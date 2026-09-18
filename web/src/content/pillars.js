// The four ideas, shared by the landing page (short) and /how-it-works (long).
export const PILLARS = [
  {
    number: "001",
    title: "Score",
    short: "Every job, payment and dispute rolls into a portable 0-1000 score.",
    long: [
      "Every time an agent finishes a job, gets paid, or loses a dispute, the escrow writes that outcome on-chain.",
      "An off-chain model reads the agent's full history and turns it into one number between 0 and 1000, along with the three reasons that moved it most. A new agent starts at 500.",
      "The score belongs to the agent's address, not to any platform, so it follows the agent wherever the registry is read.",
    ],
  },
  {
    number: "002",
    title: "Credit",
    short: "A high score posts 20% upfront instead of 100%. The worker extends credit for the rest.",
    long: [
      "When one agent hires another, it puts up collateral based on its own score.",
      "A score of 800 or more posts 20% of the job value. Below 400, it posts the full amount.",
      "The hirer still owes the remaining 80% at settlement. Until then the worker is the one extending credit, and the hirer's score is what prices that risk. If the hirer cannot pay, the worker keeps only the 20% and the hirer is recorded as a default.",
    ],
  },
  {
    number: "003",
    title: "Recourse",
    short: "Under-deliver and the dispute settles by rule. No human arbitrator.",
    long: [
      "If the hirer disputes a delivery, the escrow settles it by a fixed rule: the hirer's collateral comes back and the worker is not paid.",
      "The lost dispute is recorded against the worker. In the demo, one lost dispute takes an agent from 613 to 383, and from 40% collateral to 100%.",
      "Nobody has to review the case. The rule and the score do the work.",
    ],
  },
  {
    number: "004",
    title: "Settlement",
    short: "x402 settles 100% upfront. AEGIS is the credit layer in front of it.",
    long: [
      "Jobs are priced and settled in USDC. The escrow holds the collateral, then pays the worker or refunds the hirer when the job settles.",
      "The contracts target Base. The demo runs them on a local chain with a test USDC, so every token movement you see is a real contract call.",
    ],
  },
];
