import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Mentra · Trigger Simulator",
    page_icon="🌿",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Page background */
.stApp { background: #000000; color: #F9FAFB; }

/* Hide default streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; }

/* Section headers */
.section-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #9CA3AF;
    margin-bottom: 8px;
    margin-top: 4px;
}

/* Result card base */
.result-card {
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 12px;
    border: 1px solid transparent;
}

/* Trigger type cards */
.card-gentle  { background: #ECFDF5; border-color: #6EE7B7; }
.card-followup{ background: #EFF6FF; border-color: #93C5FD; }
.card-urgent  { background: #FFF7ED; border-color: #FDB877; }
.card-quiet   { background: #F9FAFB; border-color: #E5E7EB; }
.card-blocked { background: #FEF2F2; border-color: #FCA5A5; }

.rule-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 6px;
}
.rule-title-gentle   { color: #065F46; }
.rule-title-followup { color: #1E40AF; }
.rule-title-urgent   { color: #92400E; }
.rule-title-quiet    { color: #374151; }
.rule-title-blocked  { color: #991B1B; }

.rule-reason {
    font-size: 13px;
    color: #6B7280;
    line-height: 1.55;
    margin-bottom: 0;
}

/* Notification mockup */
.notif-wrap {
    background: white;
    border-radius: 18px;
    padding: 16px 18px;
    margin-top: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04);
}
.notif-header {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #9CA3AF;
    margin-bottom: 5px;
    display: flex;
    align-items: center;
    gap: 5px;
}
.notif-title {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
    margin-bottom: 3px;
}
.notif-body {
    font-size: 13px;
    color: #4B5563;
    line-height: 1.55;
}

/* Fired-by code */
.fired-by {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    background: rgba(0,0,0,0.04);
    border-radius: 6px;
    padding: 2px 8px;
    color: #374151;
    display: inline-block;
    margin-top: 10px;
}

/* Fatigue bar */
.fatigue-track {
    background: #E5E7EB;
    border-radius: 4px;
    height: 5px;
    width: 100%;
    margin-top: 8px;
    overflow: hidden;
}
.fatigue-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s;
}

/* Scenario pills */
.scenario-btn-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 4px;
}

/* Signal summary chips */
.chip {
    display: inline-block;
    font-size: 11px;
    background: #F3F4F6;
    border-radius: 100px;
    padding: 3px 10px;
    color: #374151;
    margin: 2px;
}
.chip-on {
    background: #D1FAE5;
    color: #065F46;
}
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Trigger logic (self-contained, no imports from reengagement.py needed)
# ─────────────────────────────────────────────────────────────────────────────

MAX_NOTIFS_PER_WEEK = 3
HIGH_DISTRESS_EMOTIONS = {"sadness", "burnout"}
ELEVATED_EMOTIONS = {"stress", "anxiety"}

RULE_MIN_DAYS = {
    "distress_checkin": 7,
    "high_stakes_followup": 1,
    "todo_checkin": 3,
    "declined_arc": 2,
    "low_engagement_nudge": 2,
    "momentum_nudge": 5,
}


def evaluate(
    days,
    notif_count,
    freq,
    emotion,
    arc,
    has_todo,
    high_stakes,
    low_engagement,
    user_silenced,
):

    fatigue_score = min(
        100,
        int((notif_count / MAX_NOTIFS_PER_WEEK) * 100 + (40 if user_silenced else 0)),
    )

    # Fatigue guard
    if user_silenced:
        return dict(
            rule="blocked",
            label="Quiet — user dismissed",
            badge="blocked",
            color="blocked",
            reason="User dismissed last notification — cooling off 48h before retrying.",
            notif=None,
            fired_by="fatigue_guard",
            fatigue_score=fatigue_score,
        )

    if notif_count >= MAX_NOTIFS_PER_WEEK:
        return dict(
            rule="blocked",
            label="Weekly cap reached",
            badge="blocked",
            color="blocked",
            reason=f"{notif_count}/{MAX_NOTIFS_PER_WEEK} notifications sent this week — hard cap hit.",
            notif=None,
            fired_by="fatigue_guard",
            fatigue_score=fatigue_score,
        )

    # Rule 1 — distress check-in
    if days >= RULE_MIN_DAYS["distress_checkin"] and emotion in HIGH_DISTRESS_EMOTIONS:
        body = (
            "The weight you were carrying last time — still there? No pressure, just wanted to check."
            if emotion == "burnout"
            else "It's been a little while. Last time felt heavy. Whenever you're ready, even just for a minute."
        )
        return dict(
            rule="distress_checkin",
            label="Distress check-in",
            badge="urgent",
            color="urgent",
            reason=f"{days}d gap + session closed on '{emotion}' — warranted gentle reach-out.",
            notif=dict(title="Checking in on you", body=body),
            fired_by=f"days >= {RULE_MIN_DAYS['distress_checkin']} AND emotion IN [sadness, burnout]",
            fatigue_score=fatigue_score,
        )

    # Rule 2 — high-stakes follow-up
    if high_stakes and RULE_MIN_DAYS["high_stakes_followup"] <= days <= 3:
        return dict(
            rule="high_stakes_followup",
            label="High-stakes follow-up",
            badge="followup",
            color="followup",
            reason=f"High-stakes event flagged + {days}d gap — right window to check how it went.",
            notif=dict(
                title="How did it go?",
                body="You had something big coming up. Thinking about you — how did it land?",
            ),
            fired_by="high_stakes = true AND 1 <= days <= 3",
            fatigue_score=fatigue_score,
        )

    # Rule 3 — todo check-in
    if has_todo and days >= RULE_MIN_DAYS["todo_checkin"]:
        verb = "It's been a week" if days >= 7 else "A few days have passed"
        return dict(
            rule="todo_checkin",
            label="Todo check-in",
            badge="followup",
            color="followup",
            reason=f"Pending commitment + {days}d gap — light nudge without pressure.",
            notif=dict(
                title="That thing you were going to try",
                body=f"{verb}. Did you get a chance to try it, or did life get in the way? Either's fine.",
            ),
            fired_by="has_todo = true AND days >= 3",
            fatigue_score=fatigue_score,
        )

    # Rule 4 — declined arc
    if (
        arc == "declined"
        and emotion in ELEVATED_EMOTIONS
        and days >= RULE_MIN_DAYS["declined_arc"]
    ):
        return dict(
            rule="declined_arc",
            label="Declined arc check-in",
            badge="urgent",
            color="urgent",
            reason=f"Session ended harder than it started (arc=declined, emotion={emotion}) + {days}d gap.",
            notif=dict(
                title="Still thinking about you",
                body="Last time felt like a lot. No agenda — just here if you want to talk it through.",
            ),
            fired_by="arc = declined AND emotion IN [stress, anxiety] AND days >= 2",
            fatigue_score=fatigue_score,
        )

    # Rule 5 — low engagement nudge
    if low_engagement and days >= RULE_MIN_DAYS["low_engagement_nudge"]:
        return dict(
            rule="low_engagement_nudge",
            label="Low-engagement nudge",
            badge="gentle",
            color="gentle",
            reason=f"Session ended early + {days}d gap — light 'door is open' nudge.",
            notif=dict(
                title="No pressure",
                body="Last time felt a little short. Whenever you want to pick back up — I'm here.",
            ),
            fired_by="low_engagement = true AND days >= 2",
            fatigue_score=fatigue_score,
        )

    # Rule 6 — momentum nudge
    if freq >= 4 and arc == "improved" and days >= RULE_MIN_DAYS["momentum_nudge"]:
        return dict(
            rule="momentum_nudge",
            label="Momentum nudge",
            badge="gentle",
            color="gentle",
            reason=f"Regular user ({freq} sessions/30d) + positive arc + {days}d gap.",
            notif=dict(
                title="You were on a good run",
                body="Last time ended well. Just here when you want to keep that going.",
            ),
            fired_by="sessions_30d >= 4 AND arc = improved AND days >= 5",
            fatigue_score=fatigue_score,
        )

    # No trigger
    reason = (
        "Session was very recent — no nudge needed."
        if days <= 1
        else f"No rule matched current signal combination (days={days}, emotion={emotion}, arc={arc})."
    )
    return dict(
        rule="no_trigger",
        label="No trigger",
        badge="quiet",
        color="quiet",
        reason=reason,
        notif=None,
        fired_by="none",
        fatigue_score=fatigue_score,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Preset scenarios
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = {
    "Burnout, 8 days silent": dict(
        days=8,
        notif_count=0,
        freq=5,
        emotion="burnout",
        arc="flat",
        has_todo=False,
        high_stakes=False,
        low_engagement=False,
        user_silenced=False,
    ),
    "Interview follow-up": dict(
        days=2,
        notif_count=0,
        freq=3,
        emotion="hopeful",
        arc="improved",
        has_todo=False,
        high_stakes=True,
        low_engagement=False,
        user_silenced=False,
    ),
    "Pending todo, 4 days": dict(
        days=4,
        notif_count=1,
        freq=4,
        emotion="neutral",
        arc="flat",
        has_todo=True,
        high_stakes=False,
        low_engagement=False,
        user_silenced=False,
    ),
    "Fatigue blocked": dict(
        days=5,
        notif_count=3,
        freq=2,
        emotion="stress",
        arc="declined",
        has_todo=True,
        high_stakes=False,
        low_engagement=False,
        user_silenced=False,
    ),
    "User dismissed": dict(
        days=3,
        notif_count=1,
        freq=3,
        emotion="anxiety",
        arc="declined",
        has_todo=False,
        high_stakes=False,
        low_engagement=False,
        user_silenced=True,
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Session state init
# ─────────────────────────────────────────────────────────────────────────────

defaults = dict(
    days=4,
    notif_count=1,
    freq=5,
    emotion="neutral",
    arc="improved",
    has_todo=True,
    high_stakes=False,
    low_engagement=False,
    user_silenced=False,
)
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
<div style="margin-bottom:28px">
  <span style="font-size:22px;font-weight:600;color:#111827;letter-spacing:-0.02em">🌿 Mentra</span>
  <span style="font-size:14px;color:#9CA3AF;margin-left:10px;font-weight:400">Re-engagement Trigger Simulator</span>
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Scenario presets
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="section-label">Quick scenarios</p>', unsafe_allow_html=True)

cols_pre = st.columns(len(SCENARIOS))
for i, (label, vals) in enumerate(SCENARIOS.items()):
    with cols_pre[i]:
        if st.button(label, use_container_width=True, key=f"pre_{i}"):
            for k, v in vals.items():
                st.session_state[k] = v
            st.rerun()

st.markdown("<div style='margin:20px 0 4px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Two-column layout: signals left | result right
# ─────────────────────────────────────────────────────────────────────────────

left, right = st.columns([1, 1], gap="large")

# ── LEFT: Signals ────────────────────────────────────────────────────────────
with left:

    st.markdown('<p class="section-label">Time & frequency</p>', unsafe_allow_html=True)

    st.session_state.days = st.slider(
        "Days since last session",
        min_value=0,
        max_value=30,
        value=st.session_state.days,
        key="_days_slider",
    )
    st.session_state.notif_count = st.slider(
        "Notifications sent this week",
        min_value=0,
        max_value=7,
        value=st.session_state.notif_count,
        key="_notif_slider",
    )
    st.session_state.freq = st.slider(
        "Sessions in last 30 days",
        min_value=0,
        max_value=20,
        value=st.session_state.freq,
        key="_freq_slider",
    )

    st.markdown("<div style='margin-top:18px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="section-label">Emotional state</p>', unsafe_allow_html=True)

    emotion_options = ["hopeful", "neutral", "stress", "anxiety", "sadness", "burnout"]
    st.session_state.emotion = st.selectbox(
        "Emotion at session close",
        emotion_options,
        index=emotion_options.index(st.session_state.emotion),
        key="_emotion_select",
    )

    arc_options = ["improved", "flat", "declined"]
    st.session_state.arc = st.selectbox(
        "Emotional arc (session trajectory)",
        arc_options,
        index=arc_options.index(st.session_state.arc),
        key="_arc_select",
    )

    st.markdown("<div style='margin-top:18px'></div>", unsafe_allow_html=True)
    st.markdown(
        '<p class="section-label">Unresolved context</p>', unsafe_allow_html=True
    )

    st.session_state.has_todo = st.toggle(
        "Pending todo from last session",
        value=st.session_state.has_todo,
        key="_todo_toggle",
    )
    st.session_state.high_stakes = st.toggle(
        "High-stakes event mentioned (interview, exam…)",
        value=st.session_state.high_stakes,
        key="_stakes_toggle",
    )
    st.session_state.low_engagement = st.toggle(
        "Session ended early (< 3 exchanges)",
        value=st.session_state.low_engagement,
        key="_engage_toggle",
    )
    st.session_state.user_silenced = st.toggle(
        "User dismissed last notification",
        value=st.session_state.user_silenced,
        key="_silenced_toggle",
    )

# ── RIGHT: Result ─────────────────────────────────────────────────────────────
with right:

    result = evaluate(
        days=st.session_state.days,
        notif_count=st.session_state.notif_count,
        freq=st.session_state.freq,
        emotion=st.session_state.emotion,
        arc=st.session_state.arc,
        has_todo=st.session_state.has_todo,
        high_stakes=st.session_state.high_stakes,
        low_engagement=st.session_state.low_engagement,
        user_silenced=st.session_state.user_silenced,
    )

    badge = result["badge"]
    color = result["color"]
    fs = result["fatigue_score"]

    # Fatigue fill color
    if fs < 40:
        fat_color = "#10B981"
    elif fs < 70:
        fat_color = "#F59E0B"
    else:
        fat_color = "#EF4444"

    st.markdown(
        '<p class="section-label">Trigger evaluation</p>', unsafe_allow_html=True
    )

    # Result card — header + reason
    st.markdown(
        f'<div class="result-card card-{color}">'
        f'<div class="rule-title rule-title-{color}">{result["label"]}</div>'
        f'<div class="rule-reason">{result["reason"]}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # Notification mockup — separate block so Streamlit can't mangle it
    if result["notif"]:
        title = result["notif"]["title"]
        body = result["notif"]["body"]
        st.markdown(
            f'<div class="notif-wrap">'
            f'<div class="notif-header">&#127807; Mentra &nbsp;&middot;&nbsp; now</div>'
            f'<div class="notif-title">{title}</div>'
            f'<div class="notif-body">{body}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    # Fired-by rule condition
    if result["fired_by"] not in ("none", "fatigue_guard"):
        st.markdown(
            f'<div class="fired-by">{result["fired_by"]}</div>',
            unsafe_allow_html=True,
        )

    # Fatigue bar
    st.markdown(
        f'<div class="fatigue-track">'
        f'<div class="fatigue-fill" style="width:{fs}%;background:{fat_color}"></div>'
        f"</div>"
        f'<div style="display:flex;justify-content:space-between;font-size:11px;color:#9CA3AF;margin-top:4px">'
        f"<span>Fatigue: {fs}/100</span>"
        f"<span>cap = 3 notifs/week</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Signal summary chips
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="section-label">Active signals</p>', unsafe_allow_html=True)

    chips = [
        (f"{st.session_state.days}d gap", True),
        (
            f"emotion: {st.session_state.emotion}",
            st.session_state.emotion in HIGH_DISTRESS_EMOTIONS | ELEVATED_EMOTIONS,
        ),
        (f"arc: {st.session_state.arc}", st.session_state.arc == "declined"),
        ("has todo", st.session_state.has_todo),
        ("high stakes", st.session_state.high_stakes),
        ("low engagement", st.session_state.low_engagement),
        ("user silenced", st.session_state.user_silenced),
        (
            f"{st.session_state.notif_count} notifs/wk",
            st.session_state.notif_count >= 2,
        ),
        (f"{st.session_state.freq} sessions/30d", False),
    ]

    chip_html = "".join(
        f'<span class="chip {"chip-on" if active else ""}">{label}</span>'
        for label, active in chips
    )
    st.markdown(f"<div>{chip_html}</div>", unsafe_allow_html=True)

    # Rule reference table
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    st.markdown(
        '<p class="section-label">All rules (priority order)</p>',
        unsafe_allow_html=True,
    )

    rules_table = [
        ("1", "distress_checkin", "days ≥ 7 AND emotion ∈ {sadness, burnout}"),
        ("2", "high_stakes_followup", "high_stakes = true AND 1 ≤ days ≤ 3"),
        ("3", "todo_checkin", "has_todo = true AND days ≥ 3"),
        (
            "4",
            "declined_arc",
            "arc = declined AND emotion ∈ {stress, anxiety} AND days ≥ 2",
        ),
        ("5", "low_engagement_nudge", "low_engagement = true AND days ≥ 2"),
        ("6", "momentum_nudge", "sessions_30d ≥ 4 AND arc = improved AND days ≥ 5"),
    ]

    active_rule = result["rule"]
    rows_html = ""
    for num, rule, condition in rules_table:
        is_active = rule == active_rule
        bg = "#ECFDF5" if is_active else "transparent"
        fw = "600" if is_active else "400"
        color_dot = "#10B981" if is_active else "#D1D5DB"
        rows_html += f"""
        <tr style="background:{bg}">
          <td style="padding:7px 10px;font-size:12px;color:#9CA3AF;font-weight:500">{num}</td>
          <td style="padding:7px 10px;font-size:12px;font-family:'DM Mono',monospace;font-weight:{fw};color:{'#065F46' if is_active else '#374151'}">{rule}</td>
          <td style="padding:7px 10px;font-size:11px;color:#6B7280;font-family:'DM Mono',monospace">{condition}</td>
          <td style="padding:7px 10px;text-align:center"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color_dot}"></span></td>
        </tr>"""

    st.markdown(
        f"""
    <table style="width:100%;border-collapse:collapse;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;font-family:'DM Sans',sans-serif">
      <thead>
        <tr style="background:#F9FAFB">
          <th style="padding:8px 10px;font-size:11px;color:#9CA3AF;font-weight:500;text-align:left">#</th>
          <th style="padding:8px 10px;font-size:11px;color:#9CA3AF;font-weight:500;text-align:left">Rule</th>
          <th style="padding:8px 10px;font-size:11px;color:#9CA3AF;font-weight:500;text-align:left">Condition</th>
          <th style="padding:8px 10px;font-size:11px;color:#9CA3AF;font-weight:500;text-align:center">Active</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """,
        unsafe_allow_html=True,
    )
