import os
import sys
import json

def main():
    """
    GitHub Action entrypoint.
    Reads inputs, runs scan, sets outputs, exits with
    appropriate code to pass or fail the CI pipeline.
    """
    model_path = os.environ.get("INPUT_MODEL_PATH", "")
    risk_threshold = int(os.environ.get("INPUT_RISK_THRESHOLD", "40"))
    num_classes = int(os.environ.get("INPUT_NUM_CLASSES", "10"))
    fail_on_detection = os.environ.get(
        "INPUT_FAIL_ON_DETECTION", "true"
    ).lower() == "true"

    print(f"ModelSentinel Security Scan")
    print(f"Model: {model_path}")
    print(f"Risk threshold: {risk_threshold}")
    print(f"Fail on detection: {fail_on_detection}")
    print("-" * 50)

    if not model_path:
        print("ERROR: No model path provided")
        sys.exit(1)

    if not os.path.exists(model_path):
        print(f"ERROR: Model file not found: {model_path}")
        sys.exit(1)

    try:
        from src.scanner.scanner_engine import scan_model
        import uuid

        scan_id = f"ci_{str(uuid.uuid4())[:6]}"
        result = scan_model(model_path, scan_id, num_classes)

        verdict = result.get("verdict", "UNKNOWN")
        risk_score = result.get("risk_score", 0)
        safe = result.get("safe_to_deploy", False)

        print(f"\nSCAN RESULTS")
        print(f"Verdict:       {verdict}")
        print(f"Risk Score:    {risk_score}/100")
        print(f"Safe to deploy: {'YES' if safe else 'NO'}")
        print(f"\nReport:\n{result.get('report', {}).get('report_text', '')[:300]}")

        # Set GitHub Action outputs
        with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
            f.write(f"verdict={verdict}\n")
            f.write(f"risk_score={risk_score}\n")
            f.write(f"safe_to_deploy={'true' if safe else 'false'}\n")

        # Fail pipeline if configured and risk too high
        if fail_on_detection and risk_score > risk_threshold:
            print(f"\nPIPELINE BLOCKED")
            print(f"Risk score {risk_score} exceeds threshold {risk_threshold}")
            print(f"Verdict: {verdict}")
            print(f"This model is NOT safe to deploy.")
            sys.exit(1)
        else:
            print(f"\nPIPELINE PASSED")
            print(f"Model cleared for deployment")
            sys.exit(0)

    except Exception as e:
        print(f"Scan failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()