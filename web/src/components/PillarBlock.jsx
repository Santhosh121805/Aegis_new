import MicroLabel from "./MicroLabel.jsx";

// One numbered block. `expanded` shows the long-form sentences used on /how-it-works.
export default function PillarBlock({ pillar, expanded = false }) {
  return (
    <article className={`card pillar ${expanded ? "pillar-expanded" : ""}`}>
      <div className="pillar-head">
        <span className="pillar-number">{pillar.number}</span>
        <MicroLabel>{pillar.title}</MicroLabel>
      </div>
      {expanded ? (
        <div className="pillar-body">
          {pillar.long.map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </div>
      ) : (
        <p className="pillar-short">{pillar.short}</p>
      )}
    </article>
  );
}
