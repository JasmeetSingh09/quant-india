// Interim privacy notice (V4-01 (b), 19 Nov 2026). Sources: components/LegalShell.jsx.
import { Shell, Section, List } from '../components/LegalShell'

export default function Privacy({ standalone = false }) {
  return (
    <Shell title="Privacy notice" standalone={standalone}>
      <p className="text-[15px] leading-relaxed">
        Quant India is an educational research tool for NSE stocks. This notice
        describes what the app stores and sends, as it works today.
      </p>

      <Section title="What we store">
        <List>
          <li>
            <b className="text-white">Your account.</b> Your email address and password, held by our
            sign-in provider (Supabase). The password is stored only as a one-way hash; we never see it.
            New accounts also store your confirmation that you are 18 or older.
          </li>
          <li>
            <b className="text-white">What you create in the app.</b> Your watchlist and its alert
            thresholds, holdings you enter, paper-trading simulations, investment theses and share
            links, stored with your account id.
          </li>
          <li>
            <b className="text-white">Email preferences.</b> If you turn on the weekly summary or
            watchlist alerts, we store your account's confirmed email address for that. For alerts we
            also keep which of your stocks were last alerted, so each move is mailed only once. Turning
            either off deletes the stored address (and, for alerts, that history).
          </li>
          <li>
            <b className="text-white">Product events.</b> For accounts that confirmed they are 18 or
            older, the app records which features are used (for example "simulation started"), with
            the account id and the time. These events never include your holdings, the stocks you
            chose, your name or your email.
          </li>
          <li>
            <b className="text-white">Abuse protection.</b> A random id saved in your browser and your
            IP address are used to limit how many requests one visitor can make. The server keeps them
            in memory for a short time; our hosting providers keep their standard request logs.
          </li>
        </List>
        <p>
          We do not collect bank, brokerage or payment details, government IDs, or your holdings at any
          broker. There are no advertising or third-party tracking scripts.
        </p>
      </Section>

      <Section title="In your browser">
        <p>
          Saved in your browser's local storage, on this device only:
        </p>
        <List>
          <li>your sign-in session and the random id above;</li>
          <li>display settings, such as a collapsed sidebar, the tabs you last opened and whether you answered the email prompt;</li>
          <li>
            what you typed into the tools, so it is still there when you come back: the stocks, weights,
            amounts and dates in the Simulator (with your last backtest result), in Portfolio Lab
            (Optimize, Simulate, Portfolio Test) and in Advanced (Risk, Options).
          </li>
        </List>
        <p>
          Tool inputs are sent to our server only when you run that tool. Signing out ends the session
          but does not clear the tool inputs; clearing your browser's site data removes everything above.
        </p>
      </Section>

      <Section title="Emails we send">
        <List>
          <li>Sign-in emails from Supabase: confirming your address and resetting your password.</li>
          <li>
            The weekly summary of your paper portfolios, only if you turned it on, and only when there is
            something to report.
          </li>
          <li>
            Watchlist alerts, only if you turned them on: one email when a stock on your own watchlist
            crosses the threshold you set. The same stock can alert again only after its move has come
            back inside the threshold.
          </li>
        </List>
        <p>Summaries and alerts go only to your own confirmed address. You can turn them off at any time.</p>
      </Section>

      <Section title="Who processes it for us">
        <List>
          <li><b className="text-white">Supabase</b>: sign-in and the database.</li>
          <li><b className="text-white">Render</b>, behind <b className="text-white">Cloudflare</b>: runs our server.</li>
          <li><b className="text-white">Vercel</b>: serves the website.</li>
          <li><b className="text-white">Google</b>: Gmail sends the summary and alert emails; Google Fonts serves the site's fonts, so your browser asks Google for them.</li>
          <li>
            <b className="text-white">Market data sources</b> (for example Yahoo Finance and news
            publishers): our server asks them for data by stock ticker. Nothing about you is sent.
          </li>
        </List>
        <p>These providers may store and process data outside India.</p>
      </Section>

      <Section title="How long we keep it">
        <List>
          <li>Account data, what you create and product events: until you delete your account.</li>
          <li>Email addresses for summaries and alerts, and the alert history: until you turn them off or delete your account.</li>
        </List>
      </Section>

      <Section title="Your choices">
        <List>
          <li>See and change your data in the app.</li>
          <li>
            <b className="text-white">Delete your account</b> from the sidebar. This erases your watchlist,
            holdings, simulations, theses, share links, email settings, alert history, product events and sign-in at once,
            and cannot be undone. One record stays: a log of the app's own portfolio warnings keeps only a
            one-way hash of a portfolio, which cannot be linked back to you once your holdings are deleted.
          </li>
          <li>
            <b className="text-white">Share links</b> show a simulated portfolio's holdings, weights and
            returns to anyone with the link, never your email or rupee amounts. To end a link, press the
            share icon on that simulation and choose Stop sharing; deleting the simulation or your account
            also ends it.
          </li>
        </List>
      </Section>

      <Section title="Age">
        <p>You must be 18 or older to create an account.</p>
      </Section>
    </Shell>
  )
}

