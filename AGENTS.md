## Design system (mandatory)

- Read `DESIGN.md` in full before any visual or UI change (styles, components, copy on the site, motion, 3D, layout). It is the source of truth alongside Figma file z5f7baVyPevXJte68oBCjV, page "Showcase v3: clear + 3D".
- Use only the tokens, type roles, motion budget and component decisions in `DESIGN.md`. Do not add colors, fonts, easing curves, libraries or effects that it doesn't list.
- If a task requires deviating from `DESIGN.md`, do the minimum, and list each deviation under a "Design deviations" heading in the PR description with the reason. Reviewers: flag any unlisted deviation (new color, gradient, glass, red on our own claims, text < 12 px, reading text darker than #9AA3AE, "example data" labels, GSAP + Framer in one component, motion outside the budget) as a blocking review comment.
- When a design decision changes, update `DESIGN.md` (including its Decision log) in the same PR.
