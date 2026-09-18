import { Link } from "react-router-dom";
import { DOCS_URL, ESCROW_URL, REGISTRY_URL, SCORING_API_URL } from "../content/links.js";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-col">
          <div className="micro">Product</div>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/how-it-works">How it works</Link>
          <a href={DOCS_URL} target="_blank" rel="noreferrer">
            Docs
          </a>
        </div>
        <div className="footer-col">
          <div className="micro">Protocol</div>
          <a href={REGISTRY_URL} target="_blank" rel="noreferrer">
            Registry
          </a>
          <a href={ESCROW_URL} target="_blank" rel="noreferrer">
            Escrow
          </a>
          <a href={SCORING_API_URL} target="_blank" rel="noreferrer">
            Scoring API
          </a>
        </div>
        <div className="footer-col">
          <div className="micro">Team</div>
          <span>Team Aura</span>
          <span>DSU DevHack 3.0</span>
        </div>
      </div>
    </footer>
  );
}
