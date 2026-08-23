import { M4TheoryJudgment as M4TheoryJudgmentView, type M4ConfirmedPlan, type M4TaskContract } from './M4TheoryJudgment'
import { createM4TheoryJudgmentGateway } from './m4TheoryJudgmentApi'

const gateway = createM4TheoryJudgmentGateway()

export interface M4TheoryJudgmentContainerProps {
  readonly task: M4TaskContract
  readonly onConfirmed?: (plan: M4ConfirmedPlan) => void
}

export function M4TheoryJudgmentContainer({ task, onConfirmed }: M4TheoryJudgmentContainerProps) {
  return <M4TheoryJudgmentView task={task} gateway={gateway} onConfirmed={onConfirmed} />
}
