"""Opt-in real Docker API test: baseline -> attack -> recovery. Never mocks DNS/HTTP."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.app import create_app, single_server


def main():
    app = create_app()
    client = app.test_client()
    def post(url, data=None):
        response = client.post(url, json=data or {})
        if response.status_code != 200:
            raise AssertionError((url, response.status_code, response.json))
        return response.json
    try:
        health = client.get("/api/health")
        assert health.status_code == 200, health.json
        assert client.post("/api/run", json={}).status_code == 409
        for phase in ["baseline", "attack", "recovery"]:
            post("/api/scenario", {"action": phase})
            result = post("/api/run")
            assert result["source"] == "live" and result["consistent"], result
            assert not result["evidence"]["collection_errors"], result["evidence"]
            plain, secure = result["results"]["plain"], result["results"]["secure"]
            expected_ip = "172.30.53.90" if phase == "attack" else "172.30.53.80"
            assert plain["dns"]["answers"] == [expected_ip], plain
            assert plain["http"]["connected_ip"] == expected_ip and plain["http"]["status"] == 200, plain
            assert plain["evidence"]["http_corroborated"], plain
            if phase == "attack":
                assert plain["interpretation"] == "accepted_fake", plain
                assert secure["dns"]["rcode"] == "SERVFAIL" and not secure["http"]["attempted"], secure
                assert secure["evidence"]["no_http_observed"] and secure["evidence"]["observed_request_count"] == 0, secure
                assert secure["http"]["preview_url"] is None
                assert client.get(f"/api/runs/{result['run_id']}/preview/secure").status_code == 404
                proof = post("/api/proof")["proof"]
                assert proof["rrsig_unchanged"]
                assert proof["records"]["authority"]["answers"] == ["172.30.53.80"]
                assert proof["records"]["tamper"]["answers"] == ["172.30.53.90"]
                assert "signature crypto failed" in result["evidence"]["dns_context"], result["evidence"]["dns_context"]
            else:
                assert secure["interpretation"] == "validated" and secure["dns"]["ad"], secure
                assert secure["http"]["connected_ip"] == "172.30.53.80"
                assert secure["evidence"]["http_corroborated"]
            for branch in [plain, secure]:
                url = branch["http"]["preview_url"]
                if url:
                    preview = client.get(url)
                    assert preview.status_code == 200
                    assert "sandbox" in preview.headers["Content-Security-Policy"]
                    assert branch["http"]["site_id"] in preview.text
            assert client.get("/api/runs/" + result["run_id"]).json == result
            print(f"PASS API {phase}: {result['run_id']} | HTTP requests={len(result['evidence']['http_access'])}", flush=True)
    finally:
        post("/api/scenario", {"action": "recovery"})
        print("Restored normal relay mode and flushed both resolvers.", flush=True)


if __name__ == "__main__":
    with single_server():
        main()
