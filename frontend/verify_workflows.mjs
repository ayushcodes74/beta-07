import puppeteer from "puppeteer";
import path from "path";

const SCREENSHOT_DIR = "C:\\Users\\madha\\.gemini\\antigravity\\brain\\e9b25bc8-a9b7-4145-9dd7-8ca0b42b382d";

async function run() {
  console.log("Launching headless Chrome...");
  const browser = await puppeteer.launch({
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu", "--window-size=1280,850"],
    defaultViewport: { width: 1280, height: 850 },
  });

  const page = await browser.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error" || msg.type() === "warn") {
      console.log(`[Browser Console ${msg.type()}]: ${msg.text()}`);
    }
  });

  try {
    // ----------------------------------------------------
    // STEP 1: Landing Page & Login
    // ----------------------------------------------------
    console.log("1. Navigating to Login Page...");
    await page.goto("http://localhost:5173/login", { waitUntil: "networkidle0" });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "01_login_page.png") });
    console.log("Captured 01_login_page.png");

    // ----------------------------------------------------
    // STEP 2: Teacher Login
    // ----------------------------------------------------
    console.log("2. Filling teacher credentials...");
    await page.type("#email", "madhavr432@gmail.com");
    await page.type("#password", "TeacherPass123!");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "02_teacher_login_filled.png") });

    console.log("Submitting login form...");
    await page.click("button.full-button");

    console.log("Waiting for /app route...");
    await page.waitForFunction(() => window.location.pathname.startsWith("/app"), { timeout: 15000 });
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "03_teacher_dashboard.png") });
    console.log("Captured 03_teacher_dashboard.png");

    // ----------------------------------------------------
    // STEP 3: Teacher Courses Screen
    // ----------------------------------------------------
    console.log("3. Navigating to Teacher Courses (/app/courses)...");
    await page.goto("http://localhost:5173/app/courses", { waitUntil: "networkidle0" });
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "04_teacher_courses.png") });
    console.log("Captured 04_teacher_courses.png");

    // ----------------------------------------------------
    // STEP 4: Teacher Assignment Editor
    // ----------------------------------------------------
    console.log("4. Navigating to Assignment Creator (/app/assignment/new)...");
    await page.goto("http://localhost:5173/app/assignment/new", { waitUntil: "networkidle0" });
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "05_teacher_assignment_creator.png") });
    console.log("Captured 05_teacher_assignment_creator.png");

    // ----------------------------------------------------
    // STEP 5: Teacher Logout
    // ----------------------------------------------------
    console.log("5. Logging out...");
    await page.click(".profile-logout");
    await page.waitForFunction(() => window.location.pathname === "/" || window.location.pathname === "/login", { timeout: 10000 });
    await new Promise((resolve) => setTimeout(resolve, 1000));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "06_logged_out.png") });
    console.log("Captured 06_logged_out.png");

    // ----------------------------------------------------
    // STEP 6: Student Login
    // ----------------------------------------------------
    console.log("6. Logging in as Student...");
    await page.goto("http://localhost:5173/login", { waitUntil: "networkidle0" });
    await page.type("#email", "ayushcodes07@gmail.com");
    await page.type("#password", "StudentPass123!");
    await page.click("button.full-button");

    console.log("Waiting for /app route...");
    await page.waitForFunction(() => window.location.pathname.startsWith("/app"), { timeout: 15000 });
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "07_student_dashboard.png") });
    console.log("Captured 07_student_dashboard.png");

    // ----------------------------------------------------
    // STEP 7: Student Assignments Screen
    // ----------------------------------------------------
    console.log("7. Navigating to Student Assignments (/app/student/assignments)...");
    await page.goto("http://localhost:5173/app/student/assignments", { waitUntil: "networkidle0" });
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "08_student_assignments.png") });
    console.log("Captured 08_student_assignments.png");

    // ----------------------------------------------------
    // STEP 8: Student Submissions Screen
    // ----------------------------------------------------
    console.log("8. Navigating to Student Submissions (/app/submissions)...");
    await page.goto("http://localhost:5173/app/submissions", { waitUntil: "networkidle0" });
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "09_student_submissions.png") });
    console.log("Captured 09_student_submissions.png");

    console.log("ALL BROWSER WORKFLOW TESTS COMPLETED SUCCESSFULLY!");
  } catch (err) {
    console.error("Browser workflow test error:", err);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "error_state.png") }).catch(() => {});
  } finally {
    await browser.close();
  }
}

run();
