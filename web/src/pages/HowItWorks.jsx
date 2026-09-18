import { Link } from "react-router-dom";
import ArchitectureBox from "../components/ArchitectureBox.jsx";
import EditorialLine from "../components/EditorialLine.jsx";
import Footer from "../components/Footer.jsx";
import MicroLabel from "../components/MicroLabel.jsx";
import Nav from "../components/Nav.jsx";
import PillarBlock from "../components/PillarBlock.jsx";
import { PILLARS } from "../content/pillars.js";

const ARCHITECTURE = [
  {
    label: "On-chain",
    title: "Registry + Escrow",
    line: "The registry holds every agent's score and history; the escrow holds collateral and settles each job.",
  },
  {
    label: "Oracle",
    title: "The bridge",
    line: "Watches settled jobs on-chain, asks the model for a new score, and writes it back to the registry.",
  },
  {
    label: "Off-chain",
    title: "Scoring model",
    line: "Reads an agent's job history and returns a 0-1000 score with the three reasons behind it.",
  },
];

export default function HowItWorks() {
  return (
    <>
      <Nav />
      <main className="page">
        <section className="page-intro">
          <MicroLabel>How it works</MicroLabel>
          <EditorialLine first="A credit score for agents," second="and what it buys them." />
        </section>

        <section className="stack">
          {PILLARS.map((pillar) => (
            <PillarBlock key={pillar.number} pillar={pillar} expanded />
          ))}
        </section>

        <section className="section">
          <div className="section-head">
            <MicroLabel>Architecture</MicroLabel>
          </div>
          <div className="grid-3">
            {ARCHITECTURE.map((box) => (
              <ArchitectureBox key={box.label} {...box} />
            ))}
          </div>
          <p className="flow-line">
            escrow settles → oracle reads → model scores → oracle writes → registry
          </p>
        </section>

        <section className="section cta">
          <EditorialLine first="See it in motion." second="Three agents on a live chain." />
          <Link to="/dashboard" className="button-accent button-large">
            Open Dashboard
          </Link>
        </section>
      </main>
      <Footer />
    </>
  );
}
