from orchestrator.config.loader import load_config

def test_restricted_actions_denied_by_default():
    c=load_config(); assert "live_order" in c.restricted_actions and c.require_verification
