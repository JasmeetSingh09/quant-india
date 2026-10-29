# Quant India: Privacy Policy (DRAFT, for legal review)

> **Draft, 2026-10-29.** This is not legal advice. It was written from what the code actually does, so
> that a lawyer can check it against the Digital Personal Data Protection Act 2023 and its Rules.
> Fill in the `[brackets]` first. The open questions are in `LEGAL_REVIEW_NOTES_2026-10-29.md`.

**Last updated:** [date]

Quant India ("we", "the app") is run by [owner's legal name], [city, India] (the "Data Fiduciary").
**Contact and grievances:** [contact email]. **Grievance Officer:** [name], [email]. We reply within
[7] days.

## 1. What we collect and why

| What | Why | Where it comes from |
|---|---|---|
| Your **email address** and a **password** | So you can sign in. The password is stored only as a one-way hash by our sign-in provider, and we never see it | You, at sign-up |
| Your **watchlist, portfolios, holdings, paper-trading simulations, investment theses** and **share links** | To provide the features you use | You, in the app |
| **Weekly-summary email preference** and the address it goes to | To send the summary you asked for | You, when you opt in |
| **Product events** (for example "simulation started" or "optimizer run"), stored with your account id and the date | To learn which features help people. These events never record your holdings, tickers you chose, your name or your email | The app, as you use it |
| A random **device id** stored in your browser, and your **IP address** | To limit request rates and stop abuse. The IP address is held only briefly in memory and in our host's standard request logs | Your browser |

We do **not** collect bank, brokerage or payment details, government IDs, or your real holdings at any
broker. We do not use advertising or third-party tracking scripts.

## 2. What we do not do
- We do not sell your data or share it for advertising.
- We do not use your portfolios to make or publish recommendations about you.
- Public leaderboards and statistics never show individual holdings.

## 3. Who processes it for us
| Provider | What it does | Where |
|---|---|---|
| Supabase | Sign-in and the database | Japan (Tokyo region) |
| Render | Runs our server | [United States, to be confirmed from the Render dashboard] |
| Vercel | Serves the website | Global CDN |
| Google (Gmail) | Sends alert and summary emails you opted into | Global |

Your data is therefore stored and processed **outside India**. [Lawyer: confirm this is permitted
under section 16 and that no notified restriction applies.]

Market data comes from public sources (for example Yahoo Finance, NSE and news feeds). We send them
stock tickers, never anything about you.

## 4. How long we keep it
- **Account data:** until you delete your account.
- **Email preference:** until you opt out. Opting out deletes the address; it does not just flag it.
- **Product events:** until you delete your account [or: for N months].
- **Host request logs:** per the provider's retention, typically up to 30 days.

## 5. Your rights
You can:
- **see and correct** your data in the app;
- **delete your account**: in the sidebar choose *Delete account* and type DELETE. This erases your
  portfolios, watchlist, theses, simulations, share links, email settings and sign-in at once, and
  it cannot be undone;
- **withdraw consent** at any time, by opting out of email or deleting your account;
- **raise a grievance** with the Grievance Officer above and, if unresolved, with the Data Protection
  Board of India;
- **nominate** someone to exercise these rights on your behalf if you die or become unable to.

One record survives deletion: a log of the app's own portfolio warnings stores only a one-way hash of
the portfolio. Once your holdings are deleted, nobody can link that hash back to you.

## 6. Children
[Lawyer: choose one.]
- (a) You must be 18 or older to create an account.
- (b) If you are under 18, a parent or guardian must give verifiable consent before you sign up, and
  we do not track or profile under-18 users.

## 7. Security
- Sign-in uses industry-standard tokens.
- The database cannot be reached directly from the internet, and every table is locked to the public
  API.
- Owner-only actions need a separate secret key.

No system is perfect. If a breach affects your data, we will tell you and the Data Protection Board
as the law requires.

## 8. Changes
If this policy changes in a way that matters, we will tell you in the app before the change takes
effect.
