---
type: skill
name: microsoft
---

# Microsoft calendar + mail

1. Azure Portal → App registrations → New (personal + work accounts).
2. Authentication → **Allow public client flows = Yes**.
3. API permissions: `User.Read`, `Calendars.Read`, `Mail.Send`, `offline_access`.
4. HUD **KEYS** → paste **Application (client) ID**. Tenant `consumers` for Outlook.com.
5. **MICROSOFT** → open the URL → enter the code.

Then briefing includes today's calendar. `desktop email_send` sends via Graph.
