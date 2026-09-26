# Senti — brand book

Senti is a watchdog that lives on your computer. It sits between you and your AI agents, checks every action before it runs, stays quiet when things are safe, and barks when something isn't. The brand is warm, loyal and calm: a good dog, not an alarm system.

## The idea

- **Senti is a dog.** "Watchdog" is already a computing term for a process that watches a system and steps in when something goes wrong. Senti is that, with a name and a face.
- **It lives with you.** Everything runs locally, so the promise is the promise of a family dog: it guards your home and never leaves it. Nothing you do is sent anywhere.
- **It barks only when it matters.** Safe actions pass silently. The bark (our alerts, our logo's sound waves) is rare, which is why people listen.

## Logo

The logo is Senti's alert face: ears up, always on. Files are in the Logos group.

- **App icon** (`senti-app-icon.svg`): cream dog on a terracotta rounded square. The primary logo. Use it on the Mac dock, the deck cover, social avatars.
- **Mark** (`senti-mark.svg`): terracotta dog on transparent, for cream or sand backgrounds.
- **Mark, cream** (`senti-mark-cream.svg`): for espresso or terracotta backgrounds.
- **The bark** (`senti-bark.svg`): shepherd-style profile, mouth open mid-bark with sage sound waves. Pairs with Blocked moments.
- **The snarl** (`senti-snarl.svg`): same profile, mouth closed and teeth showing. The warning before a bark; pairs with Ask moments.
- The bark and snarl are secondary marks for alerts, "how it works" and the deck, never the main logo.
- **Wordmark:** "Senti" set in Bricolage Grotesque SemiBold, ink or terracotta, placed to the right of the mark with a gap equal to the dog's ear width.
- **Clear space:** keep one ear-height of empty space around the mark. Minimum size 24px (16px in the menu bar, where macOS needs a single-colour template version of the head).
- **Don't:** recolour the dog outside the palette, add a shield or padlock, put the mark on busy photos, or stretch it.

## Colour

Warm, earthy, and deliberately unlike the cold blue and neon green of typical security tools.

| Colour | Hex | Role |
| --- | --- | --- |
| Terracotta | #C4623F | Brand. Logo, app icon, big numbers, headings 24px+ |
| Espresso | #2B1E18 | Text and dark surfaces (`ink`) |
| Sand | #E9D8C4 | Tinted panels, info alerts |
| Cream | #FBF6EF | The default background (`surface`) |
| Sage | #7C9A82 | Accent: bark waves, illustrations, allowed state |

Rough balance on any page or slide: 60% cream, 25% espresso, 10% terracotta, 5% sage. Terracotta at #C4623F is only 3.8:1 on cream, so body-size terracotta text uses `terracotta-text` (#A84D2E) instead. Every token's usage note says where it is legible.

## Alerts: how Senti barks

Senti has four states, and the loudness grows with the risk. Colour is never the only signal: every alert has an icon and a plain-words title.

- **Blocked** (the bark): `bark` fill, cream text and a cream warning sign. Used only when Senti stopped something. The loudest thing in the product.
- **Ask**: `surface-raised` background, 1.5px `terracotta-text` border, terracotta title and warning sign, espresso body. Used when Senti needs you to decide.
- **Allowed**: `sage-soft` background, `sage-text` label. Mostly never shown; used in the activity timeline.
- **Info**: `sand` background, `ink` text. Tips and neutral news.

Humour stays out of real alerts. No "Woof!" when someone's files are at risk; the dog's personality shows in onboarding, empty states and the app icon.

## Voice

Senti speaks in the first person, like a calm friend who noticed something. Short sentences, plain words, and always the reason.

- Do: "I stopped this. The agent tried to upload your .env file, which has 3 API keys, to an unknown website."
- Do: "Want me to let this through? The agent wants to delete 214 files in Projects/client-app."
- Don't: "Policy violation detected", "THREAT BLOCKED!!!", jargon like "exfiltration" in user-facing text.
- Name the thing (file, folder, website), say what would have happened, offer a clear choice.

## Type

- **Bricolage Grotesque** (display, headings): warm and a little quirky, like the dog. Google Fonts.
- **DM Sans** (text): friendly and very readable at small sizes. Google Fonts.
- **JetBrains Mono** (code): for the command or file path Senti is talking about.

## Shape and pattern

Soft corners (12px on buttons and alerts, 20px on cards and popups), flat colour, no gradients or glows. The one recurring motif is the **bark wave**: two or three concentric sage arcs, taken from the bark mark. Use it as a decorative element on covers and section slides, never more than once per view.

## Imagery

Show the product and the dog, not fear. Avoid hooded hackers, binary rain, padlocks, red siren lights and dark "cyber" backgrounds.
