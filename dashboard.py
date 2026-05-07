import streamlit as st
import requests
from datetime import datetime
import os

st.set_page_config(
    page_title="ModelSentinel",
    page_icon="🔍",
    layout="wide"
)

API_URL = os.environ.get("SENTINEL_API_URL", "http://localhost:8000")

# ─── Auth check ──────────────────────────────────────
from src.ui.auth_forms import show_auth_page, logout, get_auth_headers

if not show_auth_page():
    st.stop()

# ─── Styling ─────────────────────────────────────────
st.markdown("""
<style>
.big-title { font-size:2.5rem; font-weight:600; color:#00D4FF; }
.subtitle { font-size:1.1rem; color:#CCCCCC; }
.verdict-backdoored {
    background:#4a0000; border-left:4px solid #ff4444;
    padding:1rem; border-radius:0 8px 8px 0; color:#fff; margin:1rem 0;
}
.verdict-suspicious {
    background:#4a3a00; border-left:4px solid #ffd700;
    padding:1rem; border-radius:0 8px 8px 0; color:#fff; margin:1rem 0;
}
.verdict-clean {
    background:#004a1a; border-left:4px solid #44ff88;
    padding:1rem; border-radius:0 8px 8px 0; color:#fff; margin:1rem 0;
}
.metric-card {
    background:#1e2a3a; border-radius:8px; padding:1rem;
    border:1px solid #3a4a5a; text-align:center; color:#fff;
}
</style>
""", unsafe_allow_html=True)


def check_api():
    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def get_verdict_class(verdict):
    v = verdict.upper() if verdict else ""
    if "BACKDOOR" in v:
        return "verdict-backdoored"
    elif "SUSPICIOUS" in v:
        return "verdict-suspicious"
    return "verdict-clean"


def get_verdict_icon(verdict):
    v = verdict.upper() if verdict else ""
    if "BACKDOOR" in v:
        return "🚨"
    elif "SUSPICIOUS" in v:
        return "⚠️"
    return "✅"


# ─── Header ──────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown('<div class="big-title">🔍 ModelSentinel</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">AI Model Supply Chain Security Scanner'
        ' — detect backdoors before deployment</div>',
        unsafe_allow_html=True
    )
with col2:
    api_ok = check_api()
    if api_ok:
        st.success("API Online ✓")
    else:
        st.error("API Offline ✗")
    role = st.session_state.get("role", "readonly")
    st.markdown(
        f"👤 **{st.session_state.get('username', '')}** — {role.upper()}"
    )
    if st.button("Logout"):
        logout()

st.divider()

# ─── Role banner ─────────────────────────────────────
if role == "admin":
    st.info("👑 Admin — full access including scan and user management")
elif role == "analyst":
    st.info("🔍 Analyst — can upload and scan models")
else:
    st.warning("👁️ Read-Only — can view scan history only")

can_scan = role in ["admin", "analyst"]

# ─── Tabs ────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔬 Scan Model",
    "⚡ Queue Scan",
    "📊 Scan History",
    "📈 Statistics",
    "🎯 Known Attacks"
])

with tab1:
    st.subheader("Upload Model for Security Scan")
    left, right = st.columns([1, 1])

    with left:
        uploaded_file = st.file_uploader(
            "Upload PyTorch Model (.pt, .pth, .bin)",
            type=["pt", "pth", "bin"],
            disabled=not can_scan
        )

        num_classes = st.slider(
            "Number of output classes", 2, 1000, 10,
            help="How many classes does this model predict?"
        )

        st.markdown("---")
        st.markdown("**Or use test models:**")
        test_col1, test_col2 = st.columns(2)
        with test_col1:
            run_test = st.button(
                "Run Test Scan",
                use_container_width=True,
                disabled=not can_scan or not api_ok,
                help="Creates and scans backdoored + clean test models"
            )
        with test_col2:
            st.info("No file upload needed for test scan")

        if not can_scan:
            st.caption("Read-only users cannot run scans")

        scan_button = st.button(
            "Scan Uploaded Model",
            type="primary",
            use_container_width=True,
            disabled=not can_scan or not uploaded_file or not api_ok
        )

    with right:
        st.subheader("Scan Results")

        if run_test and can_scan:
            with st.spinner("Creating and scanning test models... (~2 min)"):
                try:
                    r = requests.post(
                        f"{API_URL}/scan/test",
                        headers=get_auth_headers(),
                        timeout=300
                    )
                    if r.status_code == 200:
                        data = r.json()
                        results = data.get("results", {})

                        for model_type, res in results.items():
                            v = res.get("verdict", "UNKNOWN")
                            icon = get_verdict_icon(v)
                            vc = get_verdict_class(v)
                            st.markdown(f"""
                            <div class="{vc}">
                            <strong>{icon} {model_type.upper()} MODEL</strong><br>
                            Verdict: {v} | Risk Score: {res.get('risk_score', 0)}/100<br>
                            Safe to deploy: {'✅ YES' if res.get('safe_to_deploy') else '🚫 NO'}
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.error(f"Error: {r.text}")
                except Exception as e:
                    st.error(f"Test scan failed: {str(e)}")

        elif scan_button and uploaded_file and can_scan:
            with st.spinner(f"Scanning {uploaded_file.name}... (~2 min)"):
                try:
                    r = requests.post(
                        f"{API_URL}/scan",
                        files={"file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            "application/octet-stream"
                        )},
                        params={"num_classes": num_classes},
                        headers=get_auth_headers(),
                        timeout=300
                    )
                    if r.status_code == 200:
                        result = r.json()
                        verdict = result.get("verdict", "UNKNOWN")
                        risk = result.get("risk_score", 0)
                        safe = result.get("safe_to_deploy", False)
                        icon = get_verdict_icon(verdict)
                        vc = get_verdict_class(verdict)

                        st.markdown(f"""
                        <div class="{vc}">
                        <strong style="font-size:1.3rem">{icon} {verdict}</strong><br>
                        Risk Score: {risk}/100 | Safe: {'YES ✅' if safe else 'NO 🚫'}
                        </div>
                        """, unsafe_allow_html=True)

                        st.progress(risk / 100)

                        m1, m2, m3 = st.columns(3)
                        with m1:
                            st.metric("Verdict", verdict)
                        with m2:
                            st.metric("Risk Score", f"{risk}/100")
                        with m3:
                            st.metric("Scan Time",
                                      f"{result.get('processing_time_seconds', 0)}s")

                        with st.expander("Full Threat Report", expanded=True):
                            st.text(result.get("report_summary", ""))

                        if "history" not in st.session_state:
                            st.session_state.history = []
                        st.session_state.history.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "file": uploaded_file.name,
                            "verdict": verdict,
                            "risk": risk
                        })
                    else:
                        st.error(f"Scan failed: {r.text}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        else:
            st.info("Upload a model or use test scan to see results")
            st.markdown("""
            **How ModelSentinel works:**
            1. Upload your PyTorch model file
            2. Neural Cleanse scans for backdoor triggers
            3. Activation Clustering checks for poisoned training data
            4. AI generates a human-readable threat report
            5. Get a risk score and deployment recommendation
            """)

with tab2:
    st.subheader("Scan History")
    try:
        r = requests.get(
            f"{API_URL}/scans",
            headers=get_auth_headers(),
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            scans = data.get("scans", [])
            if scans:
                for scan in scans:
                    v = scan.get("verdict", "UNKNOWN")
                    icon = get_verdict_icon(v)
                    risk = scan.get("risk_score", 0)
                    safe = "✅" if scan.get("safe_to_deploy") else "🚫"
                    st.markdown(
                        f"{icon} `{scan.get('created_at', '')[:16]}` — "
                        f"**{scan.get('file_name', 'unknown')}** → "
                        f"{v} | Risk: {risk}/100 | Deploy: {safe}"
                    )
            else:
                st.info("No scans yet — upload a model to get started")
        else:
            st.error("Could not load scan history")
    except Exception as e:
        st.error(f"Error: {str(e)}")

with tab3:
    st.subheader("Scanning Statistics")
    try:
        r = requests.get(
            f"{API_URL}/scans/stats",
            headers=get_auth_headers(),
            timeout=10
        )
        if r.status_code == 200:
            stats = r.json()
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total Scans",
                          stats.get("total_scans", 0))
            with c2:
                st.metric("Backdoored 🚨",
                          stats.get("backdoored", 0))
            with c3:
                st.metric("Suspicious ⚠️",
                          stats.get("suspicious", 0))
            with c4:
                st.metric("Clean ✅", stats.get("clean", 0))

            threat_rate = stats.get("threat_rate_percent", 0)
            st.markdown(f"**Threat Detection Rate: {threat_rate}%**")
            st.progress(threat_rate / 100)
        else:
            st.info("No statistics yet — run some scans first")
    except Exception as e:
        st.error(f"Error: {str(e)}")
        
with tab4:
    st.subheader("⚡ Queue Scan — Async Processing")
    st.info("Upload a model and get a job ID instantly. No waiting!")

    q_file = st.file_uploader(
        "Upload model for queue scanning",
        type=["pt", "pth", "bin"],
        key="queue_uploader",
        disabled=not can_scan
    )
    q_classes = st.slider("Number of classes", 2, 1000, 10,
                          key="q_classes")

    if st.button("Queue Scan", type="primary",
                 disabled=not can_scan or not q_file or not api_ok):
        try:
            r = requests.post(
                f"{API_URL}/scan/queue",
                files={"file": (
                    q_file.name,
                    q_file.getvalue(),
                    "application/octet-stream"
                )},
                params={"num_classes": q_classes},
                headers=get_auth_headers(),
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                scan_id = data.get("scan_id")
                st.success(f"Queued! Scan ID: `{scan_id}`")
                st.info(f"Poll for result at: /scan/queue/{scan_id}")
                st.session_state.last_queue_id = scan_id
            else:
                st.error(r.text)
        except Exception as e:
            st.error(str(e))

    if "last_queue_id" in st.session_state:
        st.markdown(f"**Last queued scan:** `{st.session_state.last_queue_id}`")
        if st.button("Check Result"):
            try:
                r = requests.get(
                    f"{API_URL}/scan/queue/{st.session_state.last_queue_id}",
                    headers=get_auth_headers(),
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    status = data.get("status", "unknown")
                    if status == "completed":
                        v = data.get("verdict", "UNKNOWN")
                        st.markdown(f"""
                        <div class="{get_verdict_class(v)}">
                        {get_verdict_icon(v)} {v} | Risk: {data.get('risk_score', 0)}/100
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info(f"Status: {status} — check again in a moment")
            except Exception as e:
                st.error(str(e))


with tab5:
    st.subheader("🎯 Known Backdoor Attack Patterns")
    try:
        r = requests.get(
            f"{API_URL}/attacks/known",
            headers=get_auth_headers(),
            timeout=10
        )
        if r.status_code == 200:
            attacks = r.json().get("attacks", [])
            for attack in attacks:
                severity_color = (
                    "🔴" if attack["severity"] == "CRITICAL" else "🟠"
                )
                with st.expander(
                    f"{severity_color} {attack['name']} ({attack['year']})"
                ):
                    st.markdown(f"**Description:** {attack['description']}")
                    st.markdown(f"**Detection:** {attack['detection']}")
                    st.markdown(f"**Severity:** {attack['severity']}")
                    st.markdown(f"**Research:** {attack['paper']}")
        else:
            st.error("Could not load attack database")
    except Exception as e:
        st.error(str(e))

st.divider()
st.caption("ModelSentinel — AI Model Supply Chain Security Scanner "
           "| github.com/trinadhsriram02/modelsentinel")