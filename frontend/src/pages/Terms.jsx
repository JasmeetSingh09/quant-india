// Interim terms of use (V4-01 (b), 19 Nov 2026), from Jasmeet's draft in docs/legal/.
import { Shell, Section, List } from '../components/LegalShell'
import { NOT_ADVICE } from '../components/NotAdvice'

export default function Terms({ standalone = false }) {
  return (
    <Shell title="Terms of use" standalone={standalone}>
      <Section title="What Quant India is">
        <p>
          Quant India is an educational and research tool. It applies quantitative methods to NSE market
          data, lets you build and paper-trade portfolios, and publishes its model's own track record.
        </p>
        <p className="font-medium text-white">{NOT_ADVICE}</p>
        <p>
          Nothing in the app, including scores, ranks, Top picks, alerts, simulations and warnings, is a
          recommendation to buy, sell or hold any security, an offer to do so, or advice suited to your
          circumstances.
        </p>
      </Section>

      <Section title="The models are experimental">
        <List>
          <li>
            Most of the app's signals have not been shown to predict returns. The app says which have been
            tested, and how they did, on its evidence pages.
          </li>
          <li>Backtests and simulations describe what might have happened under stated assumptions. They are not forecasts.</li>
          <li>Past performance, real or simulated, does not predict future results.</li>
          <li>Data can be late, incomplete or wrong, and comes from third-party sources we do not control.</li>
        </List>
        <p>
          If you invest real money, the decision and its results are yours alone. Consider a SEBI-registered
          adviser.
        </p>
      </Section>

      <Section title="Your account">
        <List>
          <li>You must be 18 or older to create an account.</li>
          <li>Keep your password to yourself. You are responsible for activity on your account.</li>
          <li>You can delete your account at any time from the sidebar.</li>
        </List>
      </Section>

      <Section title="Acceptable use">
        <p>Do not:</p>
        <List>
          <li>break the law;</li>
          <li>try to get into other users' data or the app's owner-only functions;</li>
          <li>overload or scrape the service;</li>
          <li>resell or republish the app's data or scores;</li>
          <li>use the app to give paid investment advice to others.</li>
        </List>
        <p>Accounts that do may be suspended.</p>
      </Section>

      <Section title="Shared portfolios">
        <p>
          A share link shows your simulated portfolio to anyone who has the link. To end it, press the
          share icon on that simulation and choose Stop sharing; deleting the simulation or your account
          also ends it. Do not share anything you would not want public.
        </p>
      </Section>

      <Section title="Third-party data">
        <p>
          Market prices, company data and news come from third parties under their own terms. They are
          provided for your personal, non-commercial use inside the app.
        </p>
      </Section>

      <Section title="No warranty">
        <p>
          The app is provided as it is. We do not promise that it is accurate, complete or always available.
        </p>
      </Section>

      <Section title="Changes">
        <p>
          We may change or stop the app. If these terms change in a way that matters, we will say so in the
          app. You can stop using the app and delete your account at any time.
        </p>
      </Section>
    </Shell>
  )
}
