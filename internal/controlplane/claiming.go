package controlplane

// Visual claim gating belongs to Store.Claim's queue query so choosing and
// reserving work remains one transaction. A "before" capture excludes a root
// execution until it is ready. A missing capture remains retryable, but never
// becomes a misleading second "before" screenshot after work has started.
