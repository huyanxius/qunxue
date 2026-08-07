import { test, expect } from '@playwright/test';

test.describe('研究任务核心流程', () => {
  test('建立空白研究任务、进入任务路由、验证任务信息、刷新后恢复相同任务ID', async ({ page }) => {
    // 1. 访问首页
    await page.goto('/');

    // 2. 点击"建立空白研究任务"按钮
    const createButton = page.getByRole('button', { name: '建立空白研究任务' });
    await expect(createButton).toBeVisible();
    await createButton.click();

    // 3. 等待跳转到研究任务页（UUID格式）
    await expect(page).toHaveURL(/\/research\/[a-f0-9-]{36}/, { timeout: 10000 });
    
    const url = page.url();
    const taskIdMatch = url.match(/\/research\/([a-f0-9-]{36})/);
    expect(taskIdMatch).toBeTruthy();
    const taskId = taskIdMatch![1];

    // 4. 等待页面稳定
    await page.waitForLoadState('networkidle');

    // 5. 验证任务信息在页面上可见
    await expect(page.getByText('研究任务已经落盘')).toBeVisible();
    await expect(page.getByText(taskId)).toBeVisible();
    
    // 精确匹配小写的 draft（排除顶部导航的 DRAFT）
    await expect(page.getByText('draft', { exact: true })).toBeVisible();
    await expect(page.getByText('direct_input', { exact: true })).toBeVisible();

    // 6. 刷新页面
    await page.reload();
    await page.waitForLoadState('networkidle');

    // 7. 验证恢复相同任务ID
    await expect(page).toHaveURL(new RegExp(`/research/${taskId}`));
    
    // 8. 验证刷新后任务信息仍然显示
    await expect(page.getByText('研究任务已经落盘')).toBeVisible();
    await expect(page.getByText(taskId)).toBeVisible();
  });
});