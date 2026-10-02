import json, subprocess, sys

def test_cli_submit_status_report(tmp_path):
    payload={"task_id":"cli-1","type":"engineering_fix","priority":"blocking","scope":"single_failure","allowed_actions":["read_repo"],"forbidden_actions":["live_order"],"success_condition":"github_ci_pass"}
    task_file=tmp_path/"task.json"; task_file.write_text(json.dumps(payload),encoding="utf-8")
    root=tmp_path/"state"
    cmd=[sys.executable,"-m","orchestrator.cli","--root",str(root),"submit",str(task_file)]
    result=subprocess.run(cmd,capture_output=True,text=True); assert result.returncode==0; assert "cli-1" in result.stdout
    result=subprocess.run([sys.executable,"-m","orchestrator.cli","--root",str(root),"status","cli-1"],capture_output=True,text=True)
    assert result.returncode==0 and "RECEIVED" in result.stdout
    result=subprocess.run([sys.executable,"-m","orchestrator.cli","--root",str(root),"report","cli-1"],capture_output=True,text=True)
    assert result.returncode==0 and "TASK_CREATED" not in result.stdout
