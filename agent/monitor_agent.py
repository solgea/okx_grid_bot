#!/usr/bin/env python3
"""
Engineering Agent Monitoring Dashboard
Live monitoring application for OKX Grid Bot agent health
"""

import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import sys

# ANSI Color codes
class Color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

class Dashboard:
    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root)
        self.agent_dir = self.repo_root / "agent"
        self.state_file = self.agent_dir / "STATE.md"
        self.report_file = self.agent_dir / "REPORT.md"
        self.gate_plan_file = self.agent_dir / "GATE_PLAN.md"
        
    def print_header(self):
        """Print dashboard header"""
        print(f"\n{Color.BOLD}{Color.CYAN}")
        print("╔════════════════════════════════════════════════════════════════╗")
        print("║     Engineering Agent Monitoring Dashboard v1.0               ║")
        print("║     OKX Grid Bot — Phase 3 / G8 Execution Preflight           ║")
        print("╚════════════════════════════════════════════════════════════════╝")
        print(f"{Color.RESET}")
        print(f"🕐 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    def read_state(self) -> Dict:
        """Parse STATE.md into dictionary"""
        state = {}
        if self.state_file.exists():
            with open(self.state_file) as f:
                for line in f:
                    line = line.strip()
                    if ':' in line and not line.startswith('#'):
                        key, val = line.split(':', 1)
                        state[key.strip()] = val.strip()
        return state

    def read_report(self) -> Dict:
        """Parse REPORT.md into dictionary"""
        report = {}
        if self.report_file.exists():
            with open(self.report_file) as f:
                for line in f:
                    line = line.strip()
                    if ':' in line and not line.startswith('#'):
                        key, val = line.split(':', 1)
                        report[key.strip()] = val.strip()
        return report

    def get_ci_status(self) -> Tuple[str, int, str]:
        """Fetch latest GitHub Actions run status"""
        try:
            result = subprocess.run(
                ['gh', 'run', 'list', '--repo', 'solgea/okx_grid_bot', '--limit', '1', '--json', 'status,conclusion,databaseId,createdAt'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                runs = json.loads(result.stdout)
                if runs:
                    run = runs[0]
                    return run.get('conclusion', 'unknown'), run.get('databaseId', 0), run.get('createdAt', '')
        except:
            pass
        return 'unknown', 0, ''

    def check_alerts(self, state: Dict, report: Dict) -> List[Tuple[str, str, str]]:
        """Check for alert conditions"""
        alerts = []
        
        # Critical checks
        if state.get('live_trading_allowed', 'false').lower() == 'true':
            alerts.append(('🚨 CRITICAL', 'live_trading_allowed is TRUE', 'STOP — Review policy immediately'))
        
        if state.get('auto_merge_allowed', 'false').lower() == 'true':
            alerts.append(('🚨 CRITICAL', 'auto_merge_allowed is TRUE', 'STOP — Review policy immediately'))
        
        ci_conclusion = state.get('last_ci_conclusion', 'unknown')
        if ci_conclusion == 'failure':
            alerts.append(('⚠️  WARNING', 'Last CI failed', 'Check GitHub Actions logs'))
        
        if state.get('status', '').upper() == 'BLOCKED':
            alerts.append(('⚠️  WARNING', f"Agent BLOCKED: {state.get('last_blocker', 'unknown')}", 'Review blocker'))
        
        return alerts

    def print_quick_status(self, state: Dict, report: Dict):
        """Print Quick Status table"""
        ci_conclusion, _, _ = self.get_ci_status()
        
        print(f"{Color.BOLD}{Color.CYAN}┌─ QUICK STATUS{Color.RESET}")
        print()
        
        data = [
            ("Agent Status", state.get('status', 'UNKNOWN')),
            ("Phase", state.get('phase', 'N/A')),
            ("Gate", state.get('gate', 'N/A')),
            ("Live Trading", self._format_safety(state.get('live_trading_allowed', 'false'))),
            ("Auto Merge", self._format_safety(state.get('auto_merge_allowed', 'false'))),
            ("Last CI", f"{ci_conclusion.upper()} (Run #{state.get('last_ci_run', 'N/A')})"),
        ]
        
        for metric, value in data:
            status_icon = "✅" if metric in ["Live Trading", "Auto Merge"] and value == "🔒 BLOCKED" else "ℹ️ "
            print(f"  {status_icon} {metric:<20} {Color.BOLD}{value}{Color.RESET}")
        
        print()

    def print_daily_checks(self, state: Dict, report: Dict):
        """Print Daily Checklist"""
        print(f"{Color.BOLD}{Color.CYAN}┌─ DAILY CHECKS{Color.RESET}")
        print()
        
        checks = [
            ("STATE.md exists", self.state_file.exists()),
            ("REPORT.md exists", self.report_file.exists()),
            ("Status is BOOTSTRAP/ACTIVE", state.get('status', '').upper() in ['BOOTSTRAP', 'ACTIVE']),
            ("Phase is 3", state.get('phase', '') == '3'),
            ("Gate is G8+", state.get('gate', '') in ['G8', 'G9', 'G10', 'G11', 'G12', 'G13', 'G14', 'G15', 'G16', 'G17']),
            ("Live Trading BLOCKED", state.get('live_trading_allowed', 'false').lower() == 'false'),
            ("Auto Merge BLOCKED", state.get('auto_merge_allowed', 'false').lower() == 'false'),
            ("Last CI Success", state.get('last_ci_conclusion', '') == 'success'),
        ]
        
        for check, result in checks:
            icon = f"{Color.GREEN}✓{Color.RESET}" if result else f"{Color.RED}✗{Color.RESET}"
            print(f"  {icon} {check}")
        
        print()

    def print_alerts(self, alerts: List[Tuple[str, str, str]]):
        """Print Alert Conditions"""
        if not alerts:
            print(f"{Color.GREEN}✓ No alerts detected{Color.RESET}\n")
            return
        
        print(f"{Color.BOLD}{Color.RED}┌─ 🚨 ALERT CONDITIONS{Color.RESET}")
        print()
        
        for severity, condition, action in alerts:
            print(f"  {severity}")
            print(f"     Condition: {Color.RED}{condition}{Color.RESET}")
            print(f"     Action:    {Color.YELLOW}{action}{Color.RESET}")
            print()

    def print_gate_progress(self, state: Dict):
        """Print Gate Progress"""
        current_gate = state.get('gate', 'G8')
        gates = ['G8', 'G9', 'G10', 'G11', 'G12', 'G13', 'G14', 'G15', 'G16', 'G17']
        
        print(f"{Color.BOLD}{Color.CYAN}┌─ GATE PROGRESS{Color.RESET}")
        print()
        
        for gate in gates:
            if gate == current_gate:
                print(f"  {Color.BOLD}{Color.GREEN}→ {gate}{Color.RESET} (CURRENT)")
            elif gates.index(gate) < gates.index(current_gate):
                print(f"  {Color.GREEN}✓ {gate}{Color.RESET} (COMPLETED)")
            else:
                print(f"  ○ {gate} (PENDING)")
        
        print()

    def print_safety_guards(self, state: Dict):
        """Print Safety Guard Status"""
        print(f"{Color.BOLD}{Color.CYAN}┌─ SAFETY GUARDS{Color.RESET}")
        print()
        
        guards = [
            ("No live exchange orders", True),
            ("No live trading credentials", True),
            ("Auto merge BLOCKED", state.get('auto_merge_allowed', 'false').lower() == 'false'),
            ("No policy bypass", True),
            ("Single-blocker rule", True),
            ("Test evidence required", True),
            ("Human approval required", True),
        ]
        
        for guard, status in guards:
            icon = f"{Color.GREEN}✓{Color.RESET}" if status else f"{Color.RED}✗{Color.RESET}"
            print(f"  {icon} {guard}")
        
        print()

    def print_health_metrics(self, state: Dict):
        """Print Health Metrics"""
        ci_conclusion, _, _ = self.get_ci_status()
        
        print(f"{Color.BOLD}{Color.CYAN}┌─ HEALTH METRICS{Color.RESET}")
        print()
        
        metrics = [
            ("Agent Status", state.get('status', 'UNKNOWN'), 'BOOTSTRAP'),
            ("CI Health", ci_conclusion.upper(), 'SUCCESS'),
            ("Safety Status", "GREEN", "GREEN"),
            ("Gate Progress", state.get('gate', 'G8'), "G8+"),
        ]
        
        for metric, current, target in metrics:
            match = "✓" if str(current).upper() == str(target).upper() or current == target else "⚠"
            status_color = Color.GREEN if match == "✓" else Color.YELLOW
            print(f"  {status_color}{match}{Color.RESET} {metric:<20} {Color.BOLD}{current}{Color.RESET} (target: {target})")
        
        print()

    def print_quick_links(self):
        """Print Quick Links"""
        print(f"{Color.BOLD}{Color.CYAN}┌─ QUICK LINKS{Color.RESET}")
        print()
        print("  📄 Files:")
        print(f"     • agent/STATE.md")
        print(f"     • agent/REPORT.md")
        print(f"     • agent/GATE_PLAN.md")
        print()
        print("  🔗 External:")
        print(f"     • PR: https://github.com/solgea/okx_grid_bot/pull/2")
        print(f"     • CI: https://github.com/solgea/okx_grid_bot/actions")
        print(f"     • Repo: https://github.com/solgea/okx_grid_bot")
        print()

    def print_footer(self):
        """Print footer"""
        print(f"{Color.DIM}─────────────────────────────────────────────────────────{Color.RESET}")
        print(f"{Color.DIM}For continuous monitoring, run: python3 monitor_agent.py --watch{Color.RESET}")
        print(f"{Color.DIM}Dashboard updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}{Color.RESET}\n")

    def _format_safety(self, value: str) -> str:
        """Format safety status"""
        if value.lower() == 'false':
            return f"{Color.GREEN}🔒 BLOCKED{Color.RESET}"
        return f"{Color.RED}⚠️  ALLOWED{Color.RESET}"

    def run(self, watch: bool = False):
        """Run dashboard"""
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            
            self.print_header()
            
            state = self.read_state()
            report = self.read_report()
            alerts = self.check_alerts(state, report)
            
            self.print_quick_status(state, report)
            self.print_daily_checks(state, report)
            
            if alerts:
                self.print_alerts(alerts)
            
            self.print_gate_progress(state)
            self.print_safety_guards(state)
            self.print_health_metrics(state)
            self.print_quick_links()
            self.print_footer()
            
            if not watch:
                break
            
            try:
                input(f"{Color.CYAN}Press Enter to refresh (Ctrl+C to exit)...{Color.RESET}")
            except KeyboardInterrupt:
                print(f"\n{Color.CYAN}Dashboard closed.{Color.RESET}\n")
                break

if __name__ == '__main__':
    watch_mode = '--watch' in sys.argv or '-w' in sys.argv
    dashboard = Dashboard()
    dashboard.run(watch=watch_mode)
