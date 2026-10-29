import sys
from pathlib import Path
import unittest
import dns.message
import dns.rrset
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from tamper import mutate

def answer(name="www.demo.test."):
    r = dns.message.make_response(dns.message.make_query(name, "A"))
    r.answer.append(dns.rrset.from_text(name, 15, "IN", "A", "172.30.53.80"))
    r.answer.append(dns.rrset.from_text(name, 15, "IN", "RRSIG",
        "A 13 3 15 20300101000000 20200101000000 12345 demo.test. AA=="))
    return r

class TamperTests(unittest.TestCase):
    def test_off_preserves_wire(self):
        r=answer(); before=r.to_wire(); output,changed=mutate(r,False)
        self.assertFalse(changed); self.assertEqual(output.to_wire(),before)
    def test_on_changes_only_target_A(self):
        r=answer(); signature=r.answer[1].to_text(); output,changed=mutate(r,True)
        self.assertTrue(changed); self.assertEqual(output.answer[0][0].address,"172.30.53.90")
        self.assertEqual(output.answer[1].to_text(),signature)
    def test_control_not_modified(self):
        r=answer("control.demo.test."); before=r.to_wire(); output,changed=mutate(r,True)
        self.assertFalse(changed); self.assertEqual(output.to_wire(),before)
    def test_dnskey_not_modified(self):
        r=dns.message.make_response(dns.message.make_query("demo.test.","DNSKEY"))
        before=r.to_wire(); output,changed=mutate(r,True)
        self.assertFalse(changed); self.assertEqual(output.to_wire(),before)
