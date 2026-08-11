import { expect, test, type Page } from "@playwright/test";

const intakeURL = process.env.FACTORY_INTAKE_E2E_ORIGIN ?? "http://127.0.0.1:17438";
const viewports = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "phone", width: 390, height: 844 },
] as const;

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(`(() => {
    const viewport = document.documentElement.clientWidth;
    const outside = [...document.querySelectorAll("a, button, summary")]
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -1 || rect.right > viewport + 1;
      })
      .map((element) => element.textContent?.trim() || element.tagName);
    return { documentFits: document.documentElement.scrollWidth <= viewport, outside };
  })()`) as { documentFits: boolean; outside: string[] };
  expect(overflow.documentFits).toBe(true);
  expect(overflow.outside).toEqual([]);
}

for (const viewport of viewports) {
  test(`shows the real intake Plan and Alerts on ${viewport.name}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
    const page = await context.newPage();

    await page.goto(`${intakeURL}/plan`);
    await expect(page.getByRole("heading", { name: "План", exact: true })).toBeVisible();
    const why = page.locator("details.why-details").first();
    await expect(why).not.toHaveAttribute("open", "");
    await why.locator("summary").click();
    await expect(why).toHaveAttribute("open", "");
    await expect(why.getByText("Владелец должен видеть обоснование только по своему запросу.")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: `test-results/screenshots/plan-${viewport.name}.png`, fullPage: true });

    await page.goto(`${intakeURL}/alerts`);
    await expect(page.getByRole("heading", { name: "Уведомления", exact: true })).toBeVisible();
    const groups = page.locator("details.alert-group");
    await expect(groups.first()).not.toHaveAttribute("open", "");
    await groups.first().locator("summary").click();
    await expect(groups.first()).toHaveAttribute("open", "");
    await page.getByRole("link", { name: "работа встала" }).click();
    await expect(page).toHaveURL(/\/alerts\?group=stuck$/);
    const selectedGroup = page.locator("details.alert-group[open]");
    await expect(selectedGroup).toHaveCount(1);
    await expect(selectedGroup.getByText("Исполнитель ждёт доступ к репозиторию.")).toBeVisible();
    await expect(selectedGroup.getByRole("link", { name: "Открыть" })).toHaveAttribute("href", "/work/stuck");
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: `test-results/screenshots/alerts-${viewport.name}.png`, fullPage: true });

    await context.close();
  });
}
