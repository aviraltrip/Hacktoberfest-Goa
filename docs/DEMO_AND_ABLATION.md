# DemoToSkill: Demo Application & Ablation Study Plan

## 1. Demo Target Application: `ScholarshipPortal`

The demo app is a lightweight, self-contained single-page web app located in `demo_app/index.html`. It simulates a real-world university scholarship portal and can be served locally with `python -m http.server 8080`.

### V1 Baseline Mode (`http://localhost:8080/`)
- **Header**: "Goa University Scholarship Portal 2026"
- **Fields**:
  - `Full name`: Text input (`id="fullName"`, `aria-label="Full name"`)
  - `Department`: Dropdown select (`id="department"`, options: Computer Science, Information Technology, Electronics, Mechanical, Civil)
  - `Graduation Year`: Dropdown select (`id="gradYear"`, options: 2026, 2027, 2028, 2029)
  - `Statement of Purpose`: Textarea (`id="sop"`)
- **Submit Button**:
  - `<button id="submitBtn" class="btn-primary" aria-label="Submit application">`
  - Visual: Paper airplane SVG icon + text `"Submit Application"`
- **On Submit**: Displays an alert banner:
  - `<div class="alert alert-success">Application received, ref #GA-8921</div>`

---

### V2 Mutated Mode (`http://localhost:8080/?v=2`)
Simulates a disruptive frontend redesign that breaks standard test automation frameworks:
1. **Renamed Label**: `"Full name"` label changed to `"Applicant"`.
2. **Scrambled IDs & Classes**: `#submitBtn` becomes `#btn_action_882`, classes change from `.btn-primary` to `.ui-footer-act-pill`.
3. **The Unsolvable Mutation (Icon-Only Button)**:
   - Button text removed completely.
   - `aria-label` attribute **completely stripped**.
   - Button contains only an inline SVG paper plane.
   - *Result for rules/BM25*: Zero text or accessible name matches in DOM. Only multimodal vision can connect the paper plane icon with the intent to "Submit application".
4. **Layout Migration**: Button is relocated out of the form container into a fixed bottom sticky footer bar (`<footer class="portal-dock">`).

---

## 2. The Ablation Study (Proving Gemma 4 is Essential)

At the hackathon presentation, judges must see that **Gemma 4 is indispensable**, not just a decorative wrapper. We run an automated ablation script (`scripts/ablation.py`) across 6 test mutations:

| Mutation # | Mutation Description | Conventional / BM25 Top-1 (No LLM) | BM25 + Gemma 4 Set-of-Marks | Why Gemma 4 Wins |
| :---: | :--- | :---: | :---: | :--- |
| **M1** | Renamed label (`Full name` -> `Applicant`) | ⚠️ Partial (matches text if lucky) | ✅ 100% | Gemma understands synonyms ("applicant" = "name"). |
| **M2** | Scrambled IDs and CSS classes | ❌ Fails (hardcoded selectors break) | ✅ 100% | Candidate extractor uses role + context, Gemma verifies visually. |
| **M3** | **Icon-only button (Text & aria-label stripped)** | ❌ **0% Complete Failure** | ✅ **100%** | **DOM text is empty.** Gemma inspects the paper airplane icon visually. |
| **M4** | Reordered DOM elements | ⚠️ 50% (clicks wrong field) | ✅ 100% | Gemma cross-checks field labels and bounding boxes. |
| **M5** | Button moved to fixed sticky footer | ❌ Fails (DOM tree hierarchy broken) | ✅ 100% | Numbered Set-of-Marks box draws directly over the footer button. |
| **M6** | Button restyled to look like a hyperlink | ⚠️ 30% (selector expects `<button>`) | ✅ 100% | Gemma identifies semantic purpose over styling. |

### Visual Proof for Judges
During the pitch, we project the **Ablation Comparison Slide**:
> *"Without Gemma 4, our self-healing recorder fails on 5 out of 6 standard UI updates (especially M3: icon-only buttons). With Gemma 4's Set-of-Marks visual reasoning, recovery rate rises to 100%."*

---

## 3. The 3-Minute Live Pitch Script

### Minute 1: The Frustration & Recording (0:00 - 1:00)
- **Speaker:** "Every Monday, university staff fill this scholarship form for 50 students manually. Existing RPA tools break if a single button changes color or moves."
- **Action:** Open DemoToSkill. Click **Start Recording**.
- **Action:** Fill ScholarshipPortal for 1 student ("Aarav Patel", "Computer Science", 2027) and click Submit.
- **Action:** Click **Stop Recording**. Live step feed shows the recorded snapshots and actions.

### Minute 2: Gemma Understands & Parameterizes (1:00 - 2:00)
- **Action:** Click **Compile Workflow**.
- **Visual:** LangGraph executes `understand`. Live SSE stream populates:
  - *"Full name"* -> Detected as variable `{{applicant_name}}`.
  - *"Department"* -> Detected as variable `{{department}}` with 5 scraped options.
  - *"Success Condition"* -> Set to `"Application received"` banner visible.
- **Action:** Open **Gemma Call Inspector** drawer: show the exact multimodal prompt and Gemma's instant JSON response.
- **Action:** Click **Run Batch** with 3 student rows. Watch the grid turn green with checkmarks and final verification screenshots.

### Minute 3: The Site Breaks, Gemma Heals (2:00 - 3:00)
- **Speaker:** "Now, the university launches a website redesign (load `?v=2`). The submit button lost its ID, lost its text, lost its aria-label, and moved to the footer."
- **Action:** Run the batch on the redesigned portal.
- **Visual:** Step 4 (Submit) fails locator resolution!
- **Visual:** Self-healing triggers instantly. The UI displays the **Set-of-Marks screenshot** with 8 numbered boxes.
- **Visual:** Box #3 (the icon-only button in the footer) is highlighted. Gemma's reason pops up:
  - *"Candidate 3 is an icon button with a paper plane inside a footer action bar, representing submission."*
- **Action:** Click **Approve Heal** (or show auto-approve). The spec is dynamically patched, the row completes, and the green success banner is verified.
- **Close:** "Record once, run for everyone, and it heals itself with Gemma 4."

