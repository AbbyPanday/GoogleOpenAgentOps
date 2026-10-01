"""
CLI Command Line Interface for GoogleOpenAgentOps.
Provides commands:
  google-openagentops gcp-check
  google-openagentops serve [--port 8000]
  google-openagentops deploy [--project PROJECT_ID] [--region REGION]
  google-openagentops setup [--ssh]
  google-openagentops pricing
"""

import argparse
import sys
from google_openagentops.pricing import MODEL_PRICING
from google_openagentops.server import launch_dashboard
from google_openagentops.context import active_context
from google_openagentops.deploy import deploy_to_cloud_run, get_ssh_setup_command


def main():
    parser = argparse.ArgumentParser(
        prog="google-openagentops",
        description="GoogleOpenAgentOps: Google Cloud Native AI Agent Observability SDK"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # gcp-check command
    subparsers.add_parser("gcp-check", help="Inspect and test auto-adapted Google Cloud Platform environment context")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Launch the local self-hosted dashboard")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind dashboard server (default: 8000)")
    serve_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")

    # alias server -> serve
    server_parser = subparsers.add_parser("server", help="Launch the local or Cloud Run dashboard server")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind dashboard server (default: 8000)")
    server_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")

    # deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Automated 1-Click deployment to Google Cloud Run")
    deploy_parser.add_argument("--project", type=str, default=None, help="Google Cloud Project ID")
    deploy_parser.add_argument("--region", type=str, default="us-central1", help="Cloud Run region (default: us-central1)")
    deploy_parser.add_argument("--service-name", type=str, default="google-openagentops-dashboard", help="Cloud Run service name")
    deploy_parser.add_argument("--port", type=int, default=8000, help="Container port (default: 8000)")
    deploy_parser.add_argument("--cpu", type=str, default="1", help="Compute vCPU (default: 1)")
    deploy_parser.add_argument("--memory", type=str, default="512Mi", help="Compute memory (default: 512Mi)")
    deploy_parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser after deployment")

    # setup command
    setup_parser = subparsers.add_parser("setup", help="Print remote SSH / Cloud Shell provisioning commands")
    setup_parser.add_argument("--repo-url", type=str, default="https://github.com/abhimanyu/GoogleOpenAgentOps.git", help="Git repository URL")

    # pricing command
    subparsers.add_parser("pricing", help="Display active Google Gemini 3.x production model token pricing")

    args = parser.parse_args()

    if args.command == "gcp-check":
        active_context.print_diagnostic_banner()

    elif args.command in ("serve", "server"):
        launch_dashboard(port=args.port, host=args.host, blocking=True)

    elif args.command == "deploy":
        deploy_to_cloud_run(
            project_id=args.project,
            region=args.region,
            service_name=args.service_name,
            port=args.port,
            cpu=args.cpu,
            memory=args.memory,
            open_browser=not args.no_browser
        )

    elif args.command == "setup":
        print("\n" + "=" * 72)
        print(" GoogleOpenAgentOps - Remote SSH & Cloud Shell Auto-Deploy Command")
        print("=" * 72)
        print("Run the following command on your GCP Compute Engine VM, Bastion host, or via SSH:\n")
        print(get_ssh_setup_command(repo_url=args.repo_url))
        print("=" * 72 + "\n")

    elif args.command == "pricing":
        print("\n" + "=" * 70)
        print("  GoogleOpenAgentOps - Active Google Gemini 3.x Production Pricing")
        print("=" * 70)
        for model_id, info in MODEL_PRICING.items():
            if model_id == "default":
                continue
            print(f"  * {model_id:<24} | Input: ${info['input_price_per_million']:.2f}/M | Output: ${info['output_price_per_million']:.2f}/M")
            print(f"    - {info['display_name']}")
        print("=" * 70 + "\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
