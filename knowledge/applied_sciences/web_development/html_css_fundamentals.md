# HTML and CSS Fundamentals

## Definition
HTML (HyperText Markup Language) defines the structure and content of web pages. CSS (Cascading Style Sheets) controls their visual presentation. Together they form the foundation of every web interface, and understanding them deeply is prerequisite for effective frontend development.

## Core HTML Concepts

- **Document Structure:** `<!DOCTYPE html>` → `<html>` → `<head>` (metadata, title, links) + `<body>` (visible content).
- **Semantic HTML:** Use elements that convey meaning: `<header>`, `<nav>`, `<main>`, `<article>`, `<section>`, `<aside>`, `<footer>`. Semantic markup improves accessibility (screen readers), SEO, and maintainability.
- **Block vs. Inline:** Block elements (`<div>`, `<p>`, `<h1>`-`<h6>`) occupy full width and start on new lines. Inline elements (`<span>`, `<a>`, `<strong>`) flow within text.
- **Forms:** `<form>`, `<input>`, `<select>`, `<textarea>`, `<button>`. Input types: text, email, password, number, checkbox, radio, file, date. Form validation: required, pattern, min, max attributes.
- **Accessibility (a11y):** ARIA attributes (role, aria-label, aria-describedby) supplement semantic HTML. Alt text on images, proper heading hierarchy, keyboard navigability, sufficient color contrast (WCAG 2.1 AA).

## Core CSS Concepts

- **Box Model:** Every element is a box — content + padding + border + margin. `box-sizing: border-box` makes width/height include padding and border.
- **Selectors:** Type (div), class (.class), ID (#id), attribute ([type="text"]), pseudo-class (:hover, :focus, :nth-child), pseudo-element (::before, ::after). Specificity: inline > ID > class > type.
- **Cascade and Inheritance:** Later rules override earlier ones (same specificity). `!important` overrides all but should be avoided. Many properties (font, color) inherit from parent.
- **Flexbox:** One-dimensional layout. Container: `display: flex`, `flex-direction`, `justify-content`, `align-items`, `gap`. Items: `flex-grow`, `flex-shrink`, `flex-basis`, `align-self`.
- **CSS Grid:** Two-dimensional layout. `grid-template-columns`, `grid-template-rows`, `grid-area`, `gap`. More powerful than flexbox for page-level layouts.
- **Responsive Design:** Media queries (`@media (max-width: 768px) { ... }`). Mobile-first approach: start with small screens, add complexity for larger. Viewport meta tag: `<meta name="viewport" content="width=device-width, initial-scale=1">`.
- **CSS Custom Properties (Variables):** `--primary-color: #2563eb;` then `var(--primary-color)`. Enable consistent theming.

## Practical Applications
- **Component design:** BEM (Block__Element--Modifier) naming convention for scalable CSS.
- **Performance:** Critical CSS (inline above-fold styles), lazy loading, CSS minification.
- **Frameworks:** Tailwind CSS (utility-first), Bootstrap (component library).
- **Animations:** CSS transitions (`transition: all 0.3s ease`) and keyframe animations (`@keyframes`).
