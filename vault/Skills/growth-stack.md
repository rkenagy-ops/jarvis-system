---
type: skill
name: growth-stack
---

# Official growth stack (6.1)

**Will do (official APIs + confirm):**
- Publer schedule/draft (`PUBLER_API_KEY` + workspace id)
- Publer follow-up / "first" comment on **your own** scheduled post
  (`stack action=comment account_id=... text='<post>' comment='<first comment>'`,
  optional `comment_delay=<minutes>`). Confirm_token gated; the approved comment text
  is what gets sent. Not available on Pinterest, TikTok, FB personal profiles or GBP.
- Klaviyo lists/metrics (`KLAVIYO_API_KEY`)
- ManyChat page info (`MANYCHAT_API_TOKEN`)
- ClickFunnels probe (`CLICKFUNNELS_API_KEY` + base URL)
- WordPress drafts/live with confirm (already). Cloudflare may still block `/wp-json` — paste in wp-admin.
- 20 named autonomy bots (`stack action=bots`)
- IBKR: watch + ENTER/NO-GO + confirm_token tickets. Never silent live fills.

**Will not do:**
- Browser hamburger to switch Instagram/Facebook accounts
- Auto-comment the feed / comment on other people's posts
- InstaPy / GramAddict / instagrapi password bots
- Extra-account farming

KEYS → paste Publer / Klaviyo / ManyChat / ClickFunnels tokens. Then `stack action=status`.
