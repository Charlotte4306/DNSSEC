"""Diagnostics must remain bounded, supplementary, and serialized with measurements."""
from copy import deepcopy
import io
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from test_api import FakeRunner
from dashboard.app import create_app
from dashboard.services.terminal_service import OUTPUT_LIMIT, catalog, command_spec, execute_terminal
from dashboard.services.docker_runner import APIError


class DiagnosticRunner(FakeRunner):
    def terminal_command(self, command_id):
        self.calls.append(("terminal", command_id))
        return {"stdout":";; status: NOERROR\n;; flags: qr rd ra ad;\n172.30.53.80\n",
                "stderr":"", "exit_code":0, "timed_out":False, "truncated":False,
                "output_complete":True, "elapsed_ms":12}


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.runner=DiagnosticRunner();self.app=create_app(self.runner,self.temp.name)
        self.app.testing=True;self.client=self.app.test_client();self.lab=self.app.extensions['lab']

    def run_command(self, command_id='secure-a'):
        return self.client.post('/api/terminal/run',json={'command_id':command_id})

    def test_catalog_is_read_only_and_does_not_expose_runner_arguments(self):
        response=self.client.get('/api/terminal/commands')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['source'],'live')
        self.assertEqual(len(response.json['commands']),7)
        self.assertTrue(all('args' not in c for c in response.json['commands']))
        self.assertEqual(self.runner.calls,[])

    def test_supplementary_command_preserves_mode_and_previous_measurement(self):
        self.client.post('/api/scenario',json={'action':'attack'})
        previous=self.client.post('/api/run',json={}).json['run_id']
        before=deepcopy(self.runner.mode);prepared=deepcopy(self.lab.prepared)
        count=len(self.runner.calls)
        response=self.run_command()
        self.assertEqual(response.status_code,200,response.json)
        data=response.json
        self.assertEqual(data['kind'],'supplementary_command')
        self.assertEqual(data['command_id'],'secure-a')
        self.assertEqual(data['executed_in'],'authority')
        self.assertEqual(data['revision'],before['changed_at'])
        self.assertIn('dig @172.30.53.30',data['command'])
        self.assertNotIn('run_id',data)
        self.assertEqual(self.runner.calls[count:],[('terminal','secure-a')])
        self.assertEqual(self.runner.mode,before)
        self.assertEqual(self.lab.prepared,prepared)
        self.assertEqual(self.lab.last_run_id,previous)

    def test_invalid_input_never_invokes_docker(self):
        for value in [None,[],{},'secure-a; id','../../etc/passwd','dig @8.8.8.8 example.com']:
            self.assertEqual(self.run_command(value).status_code,400)
        self.assertEqual(self.client.post('/api/terminal/run',json={'command_id':'secure-a','command':'id'}).status_code,400)
        self.assertEqual(self.runner.calls,[])

    def test_job_and_terminal_use_same_exclusion_lock(self):
        self.lab.reserve('test-active-measurement')
        try:
            self.assertEqual(self.run_command().status_code,409)
            self.assertEqual(self.client.post('/api/jobs',json={'action':'attack'}).status_code,409)
            self.assertEqual(self.client.get('/api/terminal/commands').status_code,200)
        finally:self.lab.release()
        self.assertEqual(self.run_command().status_code,200)

    def test_transport_error_releases_lock_and_never_fakes_success(self):
        with patch.object(self.runner,'terminal_command',side_effect=APIError('DOCKER_TIMEOUT','timeout',504)):
            response=self.run_command()
        self.assertEqual(response.status_code,504)
        self.assertFalse(self.lab.busy)
        self.assertNotIn('stdout',response.json)
        self.assertEqual(self.run_command().status_code,200)

    def test_external_change_marks_diagnostics_inconsistent(self):
        original=self.runner.terminal_command
        def changed(command_id):
            value=original(command_id);self.runner.mode['changed_at']='external';return value
        self.lab.prepared=deepcopy(self.runner.mode)
        with patch.object(self.runner,'terminal_command',side_effect=changed):response=self.run_command()
        self.assertFalse(response.json['consistent'])
        self.assertIsNone(self.lab.prepared)

    def test_origin_and_host_protection_also_apply_to_terminal(self):
        self.assertEqual(self.client.post('/api/terminal/run',json={'command_id':'dnskey'},headers={'Origin':'https://untrusted.invalid'}).status_code,403)
        self.assertEqual(self.client.get('/api/terminal/commands',headers={'Host':'untrusted.invalid'}).status_code,403)
        self.assertEqual(self.runner.calls,[])


class TerminalProcessTests(unittest.TestCase):
    def process(self,stdout=b'',stderr=b'',code=0):
        process=Mock();process.stdout=io.BytesIO(stdout);process.stderr=io.BytesIO(stderr)
        process.returncode=code
        return process

    def test_fixed_argument_list_and_actual_failure_exit_are_preserved(self):
        process=self.process(stderr=b'docker failed',code=1)
        with patch('dashboard.services.terminal_service.subprocess.Popen',return_value=process) as spawn:
            result=execute_terminal('secure-a')
        args=spawn.call_args.args[0]
        self.assertIn('authority',args)
        self.assertIn('timeout',args)
        self.assertIn('@172.30.53.30',args)
        self.assertIs(spawn.call_args.kwargs['shell'],False)
        self.assertEqual(result['exit_code'],1)
        self.assertEqual(result['stderr'],'docker failed')

    def test_output_limit_bounds_combined_streams(self):
        process=self.process(b'x'*(OUTPUT_LIMIT*2),b'y'*1000)
        with patch('dashboard.services.terminal_service.subprocess.Popen',return_value=process):result=execute_terminal('dnskey')
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['stdout'].encode())+len(result['stderr'].encode()),OUTPUT_LIMIT)

    def test_timeout_kills_cli_and_keeps_collected_output(self):
        process=self.process(stdout=b'partial output',code=-1)
        process.wait.side_effect=[subprocess.TimeoutExpired('docker',10),-1]
        with patch('dashboard.services.terminal_service.subprocess.Popen',return_value=process):result=execute_terminal('plain-a')
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['stdout'],'partial output')
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_args_list[0].kwargs,{'timeout':10})

    def test_every_catalog_entry_has_a_fixed_command(self):
        for entry in catalog():
            spec=command_spec(entry['command_id'])
            self.assertIsInstance(spec['args'],list)
            self.assertNotIn('sh',spec['args'])
        with self.assertRaises(APIError):command_spec('dnskey && cat /etc/passwd')




class TypedTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.runner=DiagnosticRunner();self.app=create_app(self.runner,self.temp.name)
        self.client=self.app.test_client()

    def test_custom_name_type_and_options_are_not_a_fixed_scenario(self):
        command='dig @relay student-17.demo.test TXT +dnssec +tcp +cdflag +noall +answer'
        spec=command_spec(command)
        self.assertEqual(spec['command'],command)
        self.assertIn('@172.30.53.20',spec['args'])
        self.assertIn('student-17.demo.test',spec['args'])
        self.assertIn('+cdflag',spec['args'])
        response=self.client.post('/api/terminal/run',json={'command':command})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['command'],command)
        self.assertIn(('terminal',command),self.runner.calls)

    def test_every_example_and_defaults_parse(self):
        for command in ['dig','dig demo.test SOA @authority +multi','dig @172.30.53.30 new_name.demo.test. AAAA +tcp','dig @plain www.demo.test A +short','logs','logs secure tamper --tail 200']:
            self.assertIsInstance(command_spec(command)['args'],list)

    def test_arbitrary_host_shell_and_unbounded_options_are_rejected(self):
        for command in ['bash','cat /etc/passwd','dig @8.8.8.8 demo.test','dig @secure evil.test','dig @secure demo.test.evil.test','dig @secure demo.test ; whoami','dig @secure demo.test\nwhoami','dig @secure demo.test +trace','dig -f /etc/passwd','dig demo.test A AAAA','logs --tail 999','logs client','logs secure --follow','dig '+('x'*513)]:
            with self.subTest(command=command):
                self.assertEqual(self.client.post('/api/terminal/run',json={'command':command}).status_code,400)
        self.assertEqual(self.runner.calls,[])

    def test_ambiguous_or_wrong_typed_body_is_rejected_before_docker(self):
        for body in [{'command':[]},{'command':None},{'command':'dig','command_id':'dnskey'},{'command':'dig','shell':True},{}]:
            self.assertEqual(self.client.post('/api/terminal/run',json=body).status_code,400)
        self.assertEqual(self.runner.calls,[])

    def test_typed_logs_remain_fixed_argv_without_shell(self):
        process=Mock();process.stdout=io.BytesIO(b'actual log');process.stderr=io.BytesIO(b'');process.returncode=0
        with patch('dashboard.services.terminal_service.subprocess.Popen',return_value=process) as spawn:
            result=execute_terminal('logs secure authority --tail 12')
        self.assertIs(spawn.call_args.kwargs['shell'],False)
        self.assertEqual(spawn.call_args.args[0][-4:],['--tail','12','secure','authority'])
        self.assertEqual(result['stdout'],'actual log')


if __name__=='__main__':unittest.main()

