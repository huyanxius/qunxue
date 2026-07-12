// 演示数据。访谈材料与受访者均为虚构,仅用于展示产品流程;
// 编码簿出处为示例格式,不指向真实文献。界面各处须保留"虚构演示材料"标识。

export interface CodeProposal {
  label: string
  quote: string
  source: string
  confidence: '高' | '中' | '低'
  rationale: string
}

export interface Segment {
  id: number
  speaker: '访' | '受'
  text: string
  proposal: CodeProposal | null
}

export type Decision =
  | { kind: 'accept' }
  | { kind: 'revise'; newLabel: string }
  | { kind: 'reject'; reason: string }

export interface CodebookEntry {
  label: string
  definition: string
}

export const CODEBOOK: CodebookEntry[] = [
  { label: '算法时间压力', definition: '受访者感知到由平台派单与倒计时机制施加的时间紧迫感,及其对身体与决策的影响。' },
  { label: '申诉无门', definition: '受访者遭遇平台判责后,反馈渠道形同虚设、无法与真人对话的经历与感受。' },
  { label: '情感劳动', definition: '为避免差评而对顾客进行的情绪管理与表演,包括压抑不满、主动示好。' },
  { label: '自主性微策略', definition: '受访者在规则缝隙中发展出的自我保护或效率策略,如挑单、抄近路、错峰。' },
  { label: '收入不稳定', definition: '对单价浮动、旺淡季差异、罚款扣款导致的收入波动的陈述。' },
  { label: '社会支持', definition: '来自骑手同伴、家人或线上社群的信息互通与情感支持。' },
  { label: '身份认同摇摆', definition: '在"自由职业者"与"被平台管着的人"之间的自我定位摇摆。' },
]

export const TRANSCRIPT_TITLE = '骑手访谈 · W-03(虚构演示材料)'

export const SEGMENTS: Segment[] = [
  {
    id: 1,
    speaker: '访',
    text: '师傅您好,咱们就随便聊聊,您平时一天大概是怎么过的?',
    proposal: null,
  },
  {
    id: 2,
    speaker: '受',
    text: '早上九点多上线,一直跑到晚上九、十点吧。中午最忙,系统一单接一单地压过来,倒计时就在屏幕上跳,你眼睛根本不敢离开手机。有一回等红灯我都在算,这个灯四十秒,我还剩六分钟,爬楼要两分钟——脑子里全是这种账。',
    proposal: {
      label: '算法时间压力',
      quote: '倒计时就在屏幕上跳,你眼睛根本不敢离开手机',
      source: '编码簿 v0.3 · 条目 01「算法时间压力」(示例)',
      confidence: '高',
      rationale: '段落聚焦派单倒计时引发的持续紧迫感,与条目定义中的"时间紧迫感对身体与决策的影响"直接对应。',
    },
  },
  {
    id: 3,
    speaker: '受',
    text: '超时一分钟就扣钱,顾客再点个"未送达",这单基本白跑。你想找平台说理,客服全是机器人,转来转去还是那几句话。我申诉过三次,没有一次有人跟我讲过一句人话。',
    proposal: {
      label: '申诉无门',
      quote: '客服全是机器人,转来转去还是那几句话',
      source: '编码簿 v0.3 · 条目 02「申诉无门」(示例)',
      confidence: '高',
      rationale: '明确陈述判责后的申诉经历与"无法与真人对话"的挫败,属条目核心情形。',
    },
  },
  {
    id: 4,
    speaker: '访',
    text: '遇到顾客态度不好的时候,您一般怎么处理?',
    proposal: null,
  },
  {
    id: 5,
    speaker: '受',
    text: '忍着呗。电话里再冲,你也得"好的好的马上到"。有一次大雨,餐洒了一点,我在楼下给顾客鞠了个躬,笑着说不好意思——其实心里憋屈得很。没办法,一个差评三十块就没了。',
    proposal: {
      label: '情感劳动',
      quote: '我在楼下给顾客鞠了个躬,笑着说不好意思——其实心里憋屈得很',
      source: '编码簿 v0.3 · 条目 03「情感劳动」(示例)',
      confidence: '高',
      rationale: '外显情绪表演与内在真实感受的落差是情感劳动的典型表征,且动机指向避免差评。',
    },
  },
  {
    id: 6,
    speaker: '受',
    text: '不过干久了也有自己的门道。哪个小区门禁难进、哪个写字楼电梯慢,心里都有数。中午高峰我专挑三公里内的单子,远单让给新手——不是欺负人,是那种单子我这个等级接了准超时。',
    proposal: {
      label: '自主性微策略',
      quote: '中午高峰我专挑三公里内的单子',
      source: '编码簿 v0.3 · 条目 04「自主性微策略」(示例)',
      confidence: '中',
      rationale: '挑单行为符合"规则缝隙中的效率策略";但"远单让给新手"亦可读作同伴互动,建议人工确认主从。',
    },
  },
  {
    id: 7,
    speaker: '访',
    text: '收入方面呢,这两年感觉怎么样?',
    proposal: null,
  },
  {
    id: 8,
    speaker: '受',
    text: '说不准。单价一直在降,夏天冬天单多点,春秋就淡。上个月扣了两次全勤,到手比前月少了一千多。家里问我一个月挣多少,我都不知道怎么报数——每个月都不一样。',
    proposal: {
      label: '收入不稳定',
      quote: '家里问我一个月挣多少,我都不知道怎么报数',
      source: '编码簿 v0.3 · 条目 05「收入不稳定」(示例)',
      confidence: '高',
      rationale: '单价下行、季节波动与罚扣叠加造成的收入不可预期,为条目定义的完整实例。',
    },
  },
  {
    id: 9,
    speaker: '受',
    text: '我们有个骑手群,两百多号人。谁被恶意差评了,群里帮着出主意;哪个站点招人、哪条路修路,消息都是群里先知道。去年我摔了一跤,群里还凑了点钱。说实话,比平台靠得住。',
    proposal: {
      label: '社会支持',
      quote: '去年我摔了一跤,群里还凑了点钱',
      source: '编码簿 v0.3 · 条目 06「社会支持」(示例)',
      confidence: '高',
      rationale: '同伴社群提供信息互通与实质互助,与条目定义吻合;"比平台靠得住"的对照值得在备忘中标记。',
    },
  },
  {
    id: 10,
    speaker: '访',
    text: '您觉得自己算是自由职业吗?',
    proposal: null,
  },
  {
    id: 11,
    speaker: '受',
    text: '平台老说我们是"自由接单"。听着是自由,可你哪天不跑,等级就掉,单价就低,这算哪门子自由?但你要说我是它的员工吧,它又什么都不认。我有时候觉得自己是老板,有时候觉得自己连个工号都不配有。',
    proposal: {
      label: '身份认同摇摆',
      quote: '我有时候觉得自己是老板,有时候觉得自己连个工号都不配有',
      source: '编码簿 v0.3 · 条目 07「身份认同摇摆」(示例)',
      confidence: '高',
      rationale: '在"自由/受控""老板/无名者"两组定位之间的显式摇摆,为条目定义的直接陈述。',
    },
  },
  {
    id: 12,
    speaker: '受',
    text: '要说盼头,就是想着再跑两年,攒点钱回县里开个小店。这行当就是吃青春饭,雨天路滑、夏天中暑,没人替你想这些,只能自己当心。',
    proposal: {
      label: '自主性微策略',
      quote: '没人替你想这些,只能自己当心',
      source: '编码簿 v0.3 · 条目 04「自主性微策略」(示例)',
      confidence: '低',
      rationale: '表层是自我保护表述,但语义重心更接近"风险自担"的结构性处境,与现有条目匹配度存疑,建议人工改判或新增条目。',
    },
  },
]

export const CODED_SEGMENTS = SEGMENTS.filter((s) => s.proposal !== null)

export const REJECT_REASONS = [
  '引文不支撑该标签',
  '标签过宽,丢失段落重点',
  '应归入另一条目',
  '材料本身不构成有效编码单元',
]
