import { Link } from "react-router-dom";
import CollateralTable from "../components/CollateralTable.jsx";
import EditorialLine from "../components/EditorialLine.jsx";
import Footer from "../components/Footer.jsx";
import MicroLabel from "../components/MicroLabel.jsx";
import Nav from "../components/Nav.jsx";
import PillarBlock from "../components/PillarBlock.jsx";
import SpecCard from "../components/SpecCard.jsx";
import StatBlock from "../components/StatBlock.jsx";
import Tag from "../components/Tag.jsx";
import { LANDING_AGENTS } from "../content/landingAgents.js";
import { PILLARS } from "../content/pillars.js";

const STATS = [
  { value: "1000", label: "Score range" },
  { value: "4", label: "Collateral tiers" },
  { value: "7", label: "Features scored" },
];

export default function Landing() {
  return (
    <>
      <Nav />
      <main className="page">
        <section className="hero">
          <h1 className="hero-title">
            <span>Credit</span>
            <span>Layer for</span>
            <span>AI Agents</span>
          </h1>
          <div className="tags">
            <Tag>USDC</Tag>
            <Tag>Base</Tag>
          </div>
          <p className="hero-pitch">Transact on credit, not cash upfront.</p>
          <p className="hero-lines">
            <span>for agents that hire other agents —</span>
            <span>post 20% instead of 100%, settle on delivery,</span>
            <span>with disputes that resolve without a human.</span>
          </p>
          <Link to="/how-it-works" className="text-link">
            Read how it works →
          </Link>
        </section>

        <section className="section">
          <div className="section-head">
            <MicroLabel>Agents / live network</MicroLabel>
          </div>
          <div className="grid-3">
            {LANDING_AGENTS.map((agent) => (
              <SpecCard key={agent.name} {...agent} />
            ))}
          </div>
        </section>

        <section className="section split">
          <EditorialLine first="Trust compounds" second="instead of resetting per platform." />
          <StatBlock stats={STATS} />
        </section>

        <section className="section split">
          <EditorialLine first="Score sets the price" second="of every job." />
          <CollateralTable />
        </section>

        <section className="section">
          <div className="grid-4">
            {PILLARS.map((pillar) => (
              <PillarBlock key={pillar.number} pillar={pillar} />
            ))}
          </div>
        </section>

        <section className="section cta">
          <EditorialLine first="Three agents, one dispute." second="Watch the scores move." />
          <Link to="/dashboard" className="button-accent button-large">
            See it running
          </Link>
        </section>
      </main>
      <Footer />
    </>
  );
}
