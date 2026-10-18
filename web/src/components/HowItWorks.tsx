import { SITE } from "../lib/copy";
import { Sign } from "./Sign";

/**
 * Decorative checkout rail (aria-hidden): two identical payment tokens travel the three steps.
 * PayCheck scans each at step 02; one passes to Pay with a green check, the other is bracketed red and stopped.
 */
function CheckoutRail() {
  return (
    <div className="how-rail" aria-hidden="true">
      <span className="hr-track">
        <span className="hr-fill" />
      </span>
      <span className="hr-node hr-n1" />
      <span className="hr-node hr-n2">
        <span className="hr-ring" />
      </span>
      <span className="hr-node hr-n3" />
      <span className="hr-token hr-pass">
        <em />
      </span>
      <span className="hr-token hr-trick">
        <em />
        <i />
        <i />
        <i />
        <i />
      </span>
      <svg className="hr-check" viewBox="0 0 24 24" width="24" height="24">
        <circle cx="12" cy="12" r="10.5" />
        <path d="M7 12.4l3.2 3.1L17.2 8.6" />
      </svg>
    </div>
  );
}

export function HowItWorks() {
  return (
    <div className="wrap">
      <section className="section" aria-labelledby="how-title">
        <Sign n="03" id="how-title">
          How it works
        </Sign>
        <CheckoutRail />
        <ol className="how-steps">
          {SITE.howSteps.map((step) => (
            <li key={step.n} className="how-step">
              <p className="micro how-n">{step.n}</p>
              <h3 className="how-title">{step.title}</h3>
              <p className="body">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
