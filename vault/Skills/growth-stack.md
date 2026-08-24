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
- 21 named autonomy bots (`stack action=bots`)
- Morning engagement run (`engage action=run`, bot-21). Comments on 2-5 posts per
  network. **Auto-posts only where the network has an official reply API:**
  X (home timeline + reply), Threads (keyword search + reply_to_id), LinkedIn
  (Comments API, needs restricted partner access).
  `engage action=draft` previews without posting; `engage action=queue` lists the
  Instagram/Facebook drafts waiting on you.
- IBKR: watch + ENTER/NO-GO + confirm_token tickets. Never silent live fills.

**Will not do:**
- Browser hamburger to switch Instagram/Facebook accounts
- Auto-commenting Instagram/Facebook feeds. Not a policy choice — Meta exposes no
  endpoint for commenting on another account's post (`/me/home` was removed,
  `publish_actions` was revoked in 2018). Every tool that claims to do it drives a
  logged-in browser or a private API, which is the action-block/ban vector.
  `engage` drafts those comments and hands you a deep link instead.
- InstaPy / GramAddict / instagrapi password bots
- Extra-account farming

KEYS → paste Publer / Klaviyo / ManyChat / ClickFunnels tokens. Then `stack action=status`.
