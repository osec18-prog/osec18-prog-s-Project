# Professor Manual

## Signing in

Go to **`/professor_login`** and use your email address and password. An
administrator creates your account; if you have never been given a password you
cannot sign in and will need one set for you.

If you sign up yourself at `/professor_signup`, tell the administrator your
employee ID so they can attach your schedules to it.

Ten wrong attempts locks you out for five minutes.

## Your dashboard

**`/professor_dashboard`** greets you by name and shows how many attendance
sessions you currently have open.

That count includes sessions you never closed, even old ones. It is not wrong —
expired codes are still rejected when scanned — but a large number usually means
you have been leaving sessions open.

## Taking attendance: the full flow

### Step 1 — Verify your identity (required, once per sign-in)

Go to **`/professor_qr`**. It shows a QR code that identifies you.

Then go to **`/verify_professor_qr`** and scan that code.

This step is mandatory. If you skip it and go straight to the generate page, the
server sends you back here. It exists so that someone who gets hold of your
signed-in browser still cannot open attendance for your classes.

### Step 2 — Generate the class QR code

Go to **`/generate_qr`**:

1. Pick the class from the list — only your scheduled classes appear.
2. Set the **date**.
3. Set the **expiration time**, in 24-hour format (`14:30`). After this time
   the code stops working.
4. Submit.

The QR code appears on screen. Project it, or let students scan it from your
laptop.

### Step 3 — Watch attendance arrive

**`/active_attendance`** lists everyone who has scanned your current session,
with their name, subject, date, time and status. Refresh to see new arrivals.

### Step 4 — Close the session

Press **Close Session** on that page when the class is over. Scans are refused
immediately afterwards, even before the expiration time.

Always close a session. Leaving it open means anyone who photographed the code
can still mark themselves present until it expires.

## Choosing an expiration time

Short. Five to ten minutes after you display the code is usually right. The
whole purpose is that a student who is not in the room cannot use a photo of the
code sent by a classmate. A code valid until 23:59 defeats that.

## Reading the attendance list

| Column | Meaning |
|---|---|
| Student ID / Name | Who scanned |
| Subject | Which class |
| Date | Which session |
| Time | When they scanned, not when class started |
| Status | Always `Present` — the system records attendance, not absence |

A student who did not scan simply has no row. There is no "absent" record.

## The mobile app

Everything above works in the Flutter app as well: sign in with the same email
and password, generate codes, watch the live list and close sessions.

## Common problems

| Problem | What is happening |
|---|---|
| Sent back to the verification page | Step 1 not completed for this sign-in. Scan your own QR first. |
| "Selected subject has no registered professor" | Your name on the schedule does not exactly match your professor record. Ask the administrator to fix it. |
| A student says the code did not work | Check whether the session expired or you closed it. Both are refused. |
| "Duplicate attendance detected" | They already scanned this session. Their attendance is recorded. |
| Your class is missing from the list | The administrator has not assigned that schedule to you. |

## What you cannot do

- Edit or delete an attendance record once it exists
- Mark a student present manually
- See other professors' sessions or attendance

Ask an administrator if a record genuinely needs correcting.
