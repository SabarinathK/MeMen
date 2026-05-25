# Notification Simulator

## Deliverable 3 — Re-Engagement Trigger Logic

This folder contains a rule-based push notification decision engine for re-engagement.
The logic decides when to send a notification and what copy to send based on session history signals.

### Signals used by the rule engine

- `days` — days since the last session
- `notif_count` — notifications sent in the last week
- `freq` — session frequency over the past 30 days
- `emotion` — emotional state at session close
- `arc` — session arc (`improved`, `flat`, `declined`)
- `has_todo` — whether the user left a follow-up task or commitment
- `high_stakes` — whether the last session included an important upcoming event
- `low_engagement` — whether the session ended feeling short or low-effort
- `user_silenced` — whether the user recently dismissed a notification

### Rule order and behavior

The simulator uses a prioritized rule chain. Only the first matching rule fires.

1. **Fatigue guard**
   - Blocks notifications when the user dismissed a previous notification
   - Blocks further sends when weekly notification cap is reached

2. **Distress check-in**
   - Fires when `days >= 7` and emotion is either `sadness` or `burnout`
   - Sends a gentle, compassionate check-in

3. **High-stakes follow-up**
   - Fires when `high_stakes` is true and `1 <= days <= 3`
   - Reconnects after an important event or milestone

4. **Todo check-in**
   - Fires when `has_todo` is true and `days >= 3`
   - Nudges gently about a pending action without pressure

5. **Declined arc check-in**
   - Fires when `arc == "declined"`, emotion is `stress` or `anxiety`, and `days >= 2`
   - Offers support after a session that closed on a difficult note

6. **Low-engagement nudge**
   - Fires when `low_engagement` is true and `days >= 2`
   - Sends a low-intensity reminder that the door is open

7. **Momentum nudge**
   - Fires when the user has `freq >= 4`, `arc == "improved"`, and `days >= 5`
   - Encourages continued progress after a positive pattern

8. **No trigger**
   - If no rule matches, no notification is sent

### Example notification copy for 3 scenarios

#### Scenario 1: Distress check-in
- Signals:
  - `days = 8`
  - `emotion = burnout`
  - `notif_count = 0`
  - `freq = 5`
  - `arc = flat`
- Trigger: `distress_checkin`
- Notification:
  - Title: **Checking in on you**
  - Body: "The weight you were carrying last time — still there? No pressure, just wanted to check."

#### Scenario 2: High-stakes follow-up
- Signals:
  - `days = 2`
  - `high_stakes = true`
  - `emotion = hopeful`
  - `arc = improved`
  - `freq = 3`
- Trigger: `high_stakes_followup`
- Notification:
  - Title: **How did it go?**
  - Body: "You had something big coming up. Thinking about you — how did it land?"

#### Scenario 3: Todo check-in
- Signals:
  - `days = 4`
  - `has_todo = true`
  - `notif_count = 1`
  - `emotion = neutral`
  - `arc = flat`
- Trigger: `todo_checkin`
- Notification:
  - Title: **That thing you were going to try**
  - Body: "A few days have passed. Did you get a chance to try it, or did life get in the way? Either's fine."

### Notes

- The simulator is intentionally conservative: the user is not contacted too often and the weekly cap is enforced.
- Supportive and empathetic language is used for distress and declined-arc scenarios.
- High-stakes and todo follow-ups are framed as gentle check-ins rather than pushy reminders.
