# Quokka launch — 2026-04-15

Bob Navarro shipped v0.1 of **Quokka**, the team's internal tool for
inspecting Dossier wiki state. Quokka reads the `.hmlr/facts.db` and
`wiki/` directory, and renders a live view of supersession chains,
orphaned pages, and pending Gardener work.

Priya Shah contributed the contradiction-visualisation panel — when two
wiki pages carry conflicting claims, Quokka draws them side by side with
the supersession graph between them. This was Priya's second shipped
feature on the team, following the supersession-chain walker from February.

Quokka is Bob's project. Access is restricted to team members; Kelvin
approved the scoped deployment.
