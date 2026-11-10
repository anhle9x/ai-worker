[Tiếng Việt](README.vi.md) | English <!-- i18n-allow -->

# Documentation

All AI Worker documents, grouped by purpose. Each one has an English file and a Vietnamese file (`.vi.md`).

| Part | Document | For |
|---|---|---|
| **I. Requirements** | [ARCHITECTURE.md](ARCHITECTURE.md), section 1: goal, scope, users, what it must do, limits, data kept | Everyone |
| | [menu-bar-spec.md](menu-bar-spec.md): menu bar icon | Developers |
| | [chrome-extension-spec.md](chrome-extension-spec.md): browser extension | Developers |
| **II. System design** | [ARCHITECTURE.md](ARCHITECTURE.md), sections 2 to 6: parts, main flows, design choices, known limits | Developers, admins |
| | [DATA-MODEL.md](DATA-MODEL.md): data design, what is stored, where, how long | Developers, admins |
| | [PERMISSIONS.md](PERMISSIONS.md): roles, who sees and does what | Developers, admins |
| **III. Install** | [INSTALL.md](INSTALL.md): what you need, first deployment, building the package, updates, settings | Admins |
| | [server/README.md](../server/README.md): installing the dashboard server | Admins |
| | [COMPONENTS.md](COMPONENTS.md): parts, requirements, versions | Admins, developers |
| | [THIRD-PARTY.md](../THIRD-PARTY.md): outside code and licenses | Admins, legal |
| **IV. User guide** | [USER-GUIDE.md](USER-GUIDE.md): staff, managers, admins | Everyone |
| | [SKILLS.md](SKILLS.md): skills and rules on every computer | Staff, admins |
| | [employee-notice.md](employee-notice.md): notice to staff about the data collected | HR, managers |
| | [chat-preferences.md](chat-preferences.md): suggested Claude chat settings | Staff |
| **V. Testing** | [TEST-PLAN.md](TEST-PLAN.md): automatic tests, manual checks, release checklist | Developers, admins |
| **VI. Operations** | [OPERATIONS.md](OPERATIONS.md): daily checks, problems, backup, upgrade and rollback, logging policy, site record | Admins |
| | [SECURITY.md](../SECURITY.md): what is protected, reporting a security problem | Everyone |
| **Project** | [CHANGELOG.md](../CHANGELOG.md), [CONTRIBUTING.md](../CONTRIBUTING.md), [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), [SUPPORT.md](../SUPPORT.md) | Contributors |

Records of each installation (server, domain, IP ranges, who holds the keys) are internal and are not kept in this repository. The template is in [OPERATIONS.md](OPERATIONS.md), section 7.
