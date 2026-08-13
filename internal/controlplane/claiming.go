package controlplane

// Visual claim gating belongs to Store.Claim's queue query so choosing and
// reserving work remains one transaction. pending/running "before" captures
// exclude a root execution; ready and missing are both terminal.
