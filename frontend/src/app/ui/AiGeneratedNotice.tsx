import { useAppLocale } from '../../i18n/AppLocaleProvider'

/**
 * 压在模型回答末尾的那一行。它回答的是"这段字是谁写的"，与来源提示不是一回事——
 * 来源提示说的是"依据从哪来"，一条回答可能两行都出现。
 *
 * 声明的措辞刻意不写"仅供参考、可能不准确"：产品的立足点是来源可核对，一句笼统的
 * 免责反而把这个立足点否掉了，所以落在"请核对来源"上。
 */
export function AiGeneratedNotice() {
  const { text } = useAppLocale()
  return (
    <p className="qx-ai-notice" data-role="ai-generated-notice">
      {text('AI 生成内容，请核对来源后使用', 'AI-generated content. Verify the sources before use.')}
    </p>
  )
}
