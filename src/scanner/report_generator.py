import os
import json
from datetime import datetime
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()


def generate_threat_report(scan_results: dict,
                            model_metadata: dict) -> dict:
    """
    Use Groq LLM to generate a human-readable threat report
    from raw scan results.

    Takes technical scanner outputs and converts them into
    clear, actionable security intelligence.
    """
    model = ChatGroq(model="llama-3.1-8b-instant")

    # Prepare scanner summary for the LLM
    nc_results = scan_results.get("neural_cleanse", {})
    ac_results = scan_results.get("activation_clustering", {})

    nc_detected = nc_results.get("backdoor_detected", False)
    ac_detected = ac_results.get("backdoor_detected", False)
    nc_confidence = nc_results.get("confidence", 0)
    ac_confidence = ac_results.get("confidence", 0)

    prompt = f"""You are a cybersecurity expert specializing in AI model security.
Analyze these machine learning model security scan results and produce a 
clear threat assessment report.

MODEL INFORMATION:
- Architecture: {model_metadata.get('architecture', 'Unknown')}
- Parameters: {model_metadata.get('num_parameters', 0):,}
- File size: {model_metadata.get('file_size_mb', 0)} MB
- Layers: {model_metadata.get('num_layers', 0)}

NEURAL CLEANSE SCAN RESULTS:
- Backdoor detected: {nc_detected}
- Confidence: {nc_confidence}%
- Anomaly index: {nc_results.get('anomaly_index', 0)}
- Suspected target class: {nc_results.get('suspected_target_class', 'None')}
- Details: {'; '.join(nc_results.get('details', []))}

ACTIVATION CLUSTERING SCAN RESULTS:
- Backdoor detected: {ac_detected}
- Confidence: {ac_confidence}%
- Suspicious classes: {ac_results.get('suspicious_classes', [])}
- Details: {'; '.join(ac_results.get('details', []))}

Write a security threat report with exactly these sections:

THREAT VERDICT: [CLEAN / SUSPICIOUS / BACKDOORED]
RISK SCORE: [0-100]
CONFIDENCE: [percentage]
EXECUTIVE SUMMARY: [2-3 sentences for non-technical stakeholders]
TECHNICAL FINDINGS: [what each scanner found and what it means]
ATTACK SCENARIO: [if backdoor detected, describe how it could be exploited]
RECOMMENDED ACTION: [specific steps the team should take immediately]
SAFE TO DEPLOY: [YES / NO / REVIEW REQUIRED]"""

    response = model.invoke(prompt)
    report_text = response.content

    # Parse risk score from report
    risk_score = _extract_risk_score(report_text, nc_detected,
                                      ac_detected,
                                      nc_confidence, ac_confidence)
    verdict = _extract_verdict(report_text, nc_detected, ac_detected)

    return {
        "report_text": report_text,
        "risk_score": risk_score,
        "verdict": verdict,
        "generated_at": datetime.now().isoformat(),
        "scan_summary": {
            "neural_cleanse_detected": nc_detected,
            "activation_clustering_detected": ac_detected,
            "both_methods_agree": nc_detected == ac_detected
        }
    }


def _extract_risk_score(report_text: str, nc_detected: bool,
                         ac_detected: bool,
                         nc_conf: float, ac_conf: float) -> int:
    """Calculate risk score from detection results."""
    import re
    # Try to extract from report
    match = re.search(r'RISK SCORE[:\s]+(\d+)', report_text,
                      re.IGNORECASE)
    if match:
        return min(int(match.group(1)), 100)

    # Calculate from detections
    if nc_detected and ac_detected:
        return min(int((nc_conf + ac_conf) / 2) + 20, 100)
    elif nc_detected or ac_detected:
        conf = nc_conf if nc_detected else ac_conf
        return min(int(conf * 0.7), 80)
    else:
        return min(int((nc_conf + ac_conf) / 4), 25)


def _extract_verdict(report_text: str, nc_detected: bool,
                      ac_detected: bool) -> str:
    """Extract verdict from report text."""
    import re
    match = re.search(
        r'THREAT VERDICT[:\s]+(CLEAN|SUSPICIOUS|BACKDOORED)',
        report_text, re.IGNORECASE
    )
    if match:
        return match.group(1).upper()

    if nc_detected and ac_detected:
        return "BACKDOORED"
    elif nc_detected or ac_detected:
        return "SUSPICIOUS"
    return "CLEAN"