# Student Manual

## Creating your account

Go to **`/signup`** and give your student ID, full name, email and a password.
Your student ID must be unique — if it is already registered, you already have
an account.

Your password is stored scrambled and cannot be recovered, only replaced. If you
forget it, ask an administrator to set a new one.

## Signing in

Go to **`/login`** with your student ID and password. Ten wrong attempts locks
you out for five minutes.

## Your dashboard

**`/dashboard`** is the home page after signing in, with links to your schedule,
attendance record, announcements and the QR scanner.

## Marking attendance

Your professor displays a QR code in class. You have two ways to scan it.

### In the browser

1. Go to **`/scan_qr`**
2. Allow camera access when asked
3. Point the camera at the code

You will see one of:

| Message | Meaning |
|---|---|
| Attendance Recorded Successfully | Done. You are marked present. |
| Duplicate attendance detected | You already scanned this class. You are present — scanning again changes nothing. |
| QR code expired | The code passed its time limit. Ask your professor. |
| Attendance session is not active | The professor closed the session. |
| Invalid QR code | Not a CampusConnect+ code. |

### In the mobile app

Sign in with the same student ID and password and use the scanner there.

**If your phone has no signal**, the app saves the scan on the device and sends
it automatically once you are back online. The screen tells you when this
happens. You do not need to scan again — the app prevents your attendance being
recorded twice.

### If you scan before signing in

You will be taken to the login page. Sign in and your attendance is recorded
straight away — you do not need to scan the code again.

## Your attendance record

**`/student_attendance`** lists every class you have attended: subject,
professor, date, time and status, newest first.

Only classes you attended appear. There are no "absent" rows — a class you
missed simply is not listed.

If a class you attended is missing, your scan did not register. Tell your
professor; you cannot add it yourself.

## Your schedule

**`/student_schedule`** shows subjects, professors, days, times and rooms.

The ordering is currently unreliable — days and times sort as text, so the list
may read Friday before Monday, and 10:00 AM before 8:00 AM. Read the day column
rather than trusting the order.

## Announcements

**`/student_announcements`** shows notices from the administration, newest
first. They also appear in the mobile app.

## Signing out

Use **Logout**. On a shared or campus computer, always do this — closing the tab
is not enough.

## Common problems

| Problem | What to do |
|---|---|
| Camera does not open | Allow camera permission in your browser, and make sure the page is not open in a second tab. |
| "Too many login attempts" | Wait five minutes. |
| Page says the form expired | Reload the page and try again. |
| Scanned but nothing happened | Check `/student_attendance`. If it is not there, tell your professor before leaving. |
| Cannot reach the site on your phone | You must be on the same Wi-Fi as the server, and use the address your professor gives you, not `localhost`. |

## Your privacy

The system stores your student ID, name, email, class schedule and attendance
records. Your password is stored scrambled and nobody — including
administrators — can read it.
