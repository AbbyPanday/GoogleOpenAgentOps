"""
Multi-Solution Google ADK (Agent Development Kit) Observability Example.
Demonstrates two independent Google ADK Agent solutions (e.g., Customer Support & Financial Auditor)
both registering and emitting correlated telemetry into a central GoogleOpenAgentOps Cloud Run dashboard.
"""

import time
import google_openagentops as agentops
from google_openagentops.integrations.adk import GoogleADKTracker

def main():
    print("========================================================================")
    print(" GoogleOpenAgentOps - Multi-Solution Google ADK Observability")
    print("========================================================================")

    # 1. Initialize central GoogleOpenAgentOps environment
    session = agentops.init(project_id="gcp-adk-enterprise-demo")

    # 2. Solution A: Customer Support Bot (using Gemini 3.5 Flash for speed)
    support_solution = GoogleADKTracker(
        solution_id="sol-customer-support",
        solution_name="SupportBot-ADK",
        default_model="gemini-3.5-flash"
    )

    # 3. Solution B: Financial Auditor Agent (using Gemini 3.8 Flash for deep reasoning)
    auditor_solution = GoogleADKTracker(
        solution_id="sol-financial-auditor",
        solution_name="FinancialAuditor-ADK",
        default_model="gemini-3.8-flash"
    )

    # Instrument Solution A: Triage Agent
    @support_solution.track_agent(agent_name="TicketTriageAgent")
    def triage_customer_ticket(ticket_text: str):
        print(f"[*] [Solution A: SupportBot] Triaging ticket: '{ticket_text}'")
        time.sleep(0.05)
        # Determine if financial audit is needed
        if "refund" in ticket_text.lower() or "audit" in ticket_text.lower():
            # Handoff to Solution B
            support_solution.record_handoff(
                target_agent="FinancialAuditor-ADK",
                context={"ticket": ticket_text, "action": "Escalate to finance"}
            )
            return {"escalate_to": "FinancialAuditor", "priority": "CRITICAL"}
        return {"status": "RESOLVED_LOCALLY"}

    # Instrument Solution B: Audit Tool
    @auditor_solution.track_tool(tool_name="VerifyLedgerTransaction")
    def verify_ledger(transaction_id: str):
        print(f"[*] [Solution B: FinancialAuditor] Querying BigQuery ledger for TX: {transaction_id}")
        time.sleep(0.03)
        return {"transaction_id": transaction_id, "amount_usd": 450.00, "authorized": True}

    # Instrument Solution B: Auditor Agent
    @auditor_solution.track_agent(agent_name="ReconciliationAgent")
    def run_financial_audit(ticket_context: dict):
        print(f"[*] [Solution B: FinancialAuditor] Running audit reconciliation...")
        tx_result = verify_ledger("TX-99842")
        return {
            "decision": "APPROVED_REFUND",
            "audit_trail": tx_result,
            "reasoning": "Transaction confirmed in BigQuery ledger with valid auth."
        }

    # Execute end-to-end multi-solution scenario
    triage_result = triage_customer_ticket("Customer requesting $450 refund for double charge on invoice #8812")
    if triage_result.get("escalate_to") == "FinancialAuditor":
        audit_result = run_financial_audit(triage_result)
        print(f"[+] Final Multi-Solution Outcome: {audit_result['decision']}")

    # Check metrics
    current_sess = agentops.tracker.get_session(session.session_id)
    print("\n" + "-" * 72)
    print(f" Total Cross-Solution Spans: {len(current_sess.spans)}")
    print(f" Registered Solutions:      {[s['solution_name'] for s in agentops.tracker.get_solutions()]}")
    print(f" Total Tokens Consumed:     {current_sess.metrics.total_tokens}")
    print(f" Estimated Gemini 3.x Cost: ${current_sess.metrics.total_cost_usd:.6f}")
    print("-" * 72 + "\n")

if __name__ == "__main__":
    main()
