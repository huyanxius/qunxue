import surveyCover from '../../assets/research-tools/survey-analysis.webp'
import theoryCover from '../../assets/research-tools/qualitative-coding.webp'
import interviewCover from '../../assets/research-tools/interview-notes.webp'
import libraryCover from '../../assets/workbench/knowledge-library-hero.webp'
export const courseArtwork: Record<string, string> = { 'social-research': surveyCover, 'sociological-thinking': theoryCover, 'qualitative-reading': interviewCover, library: libraryCover }
import { createCourse, uploadCourseDocument } from '../../modules/shared-knowledge'

export type CourseChapter = { title: string; duration: number; objective: string; paragraphs: string[]; exercise: string; checklist: string[] }
export type CourseTemplate = { id: string; category: string; title: string; subtitle: string; description: string; level: string; outcomes: string[]; chapters: CourseChapter[] }

export const courseTemplates: CourseTemplate[] = [
  { id: 'social-research', category: '研究方法', title: '社会调查方法', subtitle: '从生活问题到可检验的研究', description: '围绕校园生活中的具体问题，完成问题界定、抽样、问卷与结果解释。用一套连贯案例练习研究设计。', level: '基础入门', outcomes: ['把宽泛的兴趣转化为可研究的问题', '说明样本选择与测量的局限', '用证据支持结论并交代适用范围'], chapters: [
    { title: '从现象提出研究问题', duration: 45, objective: '区分研究主题、研究问题和可观察的指标。', paragraphs: ['“大学生的学习生活”是一个主题，还不是一个能直接收集资料回答的问题。问题需要指明研究对象、关注的关系与发生的情境。例如：在同一所学校，大一学生每周参加社团的时间与其主观归属感有怎样的关系？', '把“归属感”变成可观察指标时，可以分别询问是否有可求助的同伴、是否愿意参与集体活动、是否感到被接纳。多个指标并不自动构成有效量表，仍要检查它们是否表达了同一概念。', '好的研究问题不预先写入答案。“为什么社团一定能提升归属感”已经假定了因果关系；更稳妥的提问允许出现无关系、反向关系和其他解释。'], exercise: '把“短视频影响大学生”改写成一个研究问题，说明对象、变量、情境及两种可能的解释。', checklist: ['研究对象明确', '核心概念可观察', '问题没有预设结论'] },
    { title: '抽样与调查伦理', duration: 45, objective: '理解总体、样本和选择偏差，设计可执行的招募方式。', paragraphs: ['总体是希望解释的一组对象，样本是实际进入研究的人。把问卷发到自己的社团群，得到的是容易接触的人，不等于全校学生。样本很大，也不能自动修复招募方式导致的偏差。', '可以先列出年级、专业等可能影响研究问题的差异，再说明招募如何覆盖这些差异。若只能做便利抽样，应坦诚写出边界，而不把结论推向所有大学生。', '调查开始前说明目的、用途、所需时间和退出方式。尽量减少收集姓名、联系方式等不必要信息；参与者可以跳过敏感问题。课堂作业中的同意参与不能替代对正式研究伦理要求的核对。'], exercise: '你准备调查校园夜间自习。只在图书馆门口招募会遗漏哪些人？提出一个更合适且可执行的方案。', checklist: ['区分样本与总体', '说明遗漏对象', '交代自愿参与与隐私安排'] },
    { title: '设计问卷与访谈提纲', duration: 50, objective: '识别诱导、双重提问与模糊时间范围。', paragraphs: ['“你是否支持学校改善食堂和宿舍？”把两个事项放在一个问题里。回答者可能支持其中一个、反对另一个，因此需要拆开。提问应使用参与者能理解的语言，尽量避免带有评价的词。', '“你经常运动吗？”缺少明确时间与行为定义。可以改为“过去七天，你有几天进行了至少二十分钟的运动？”更清楚的题目仍可能受到回忆偏差影响。', '访谈提纲先从具体经历开始，再追问含义和背景。与其问“你是不是因为焦虑才刷视频”，不如问“回想最近一次长时间刷视频，当时发生了什么？”预测试可以发现理解差异和遗漏选项。'], exercise: '改写三个问题：你是否非常支持读书？你喜欢老师和教材吗？你经常参加活动吗？并解释每处修改。', checklist: ['一题只问一件事', '时间范围明确', '选项与措辞保持中性'] },
    { title: '解释结果与表达边界', duration: 40, objective: '区分相关与因果，提出替代解释。', paragraphs: ['参加辅导班的学生平均成绩更高，只表明两组在观察结果上不同。原有成绩、学习动机和家庭资源都可能同时影响是否参加辅导班及最终成绩。', '比较参加前的水平、记录潜在混杂因素，或在适当条件下安排对照设计，可以帮助评估解释；一种设计也不必然排除所有偏差。报告时应交代样本来源、样本量、测量方式和缺失情况。', '讨论部分可以依次回答：数据支持什么、不能支持什么、还需要什么证据。把局限说清楚是研究结论的一部分，不是附在文末的客套话。'], exercise: '为“每天运动的学生睡眠更好”写一段结果解释，包含一个替代解释和一个后续研究方案。', checklist: ['没有将相关直接写成因果', '包含替代解释', '结论范围与证据一致'] },
  ] },
  { id: 'sociological-thinking', category: '社会学基础', title: '社会学的观察与解释', subtitle: '在日常经验中看见社会结构', description: '从课堂互动、群体规范与社会角色出发，用具体观察建立概念与经验之间的联系。', level: '基础入门', outcomes: ['从具体互动描述社会现象', '区分经验描述与概念解释', '使用反例检验自己的解释'], chapters: [
    { title: '从个人经验到社会问题', duration: 45, objective: '将个人经历放回制度与关系背景。', paragraphs: ['同样是课堂沉默，不同学生可能出于没有准备、害怕被评价、语言习惯或对课堂规则的理解。社会学分析先准确描述情境，再考虑这些行动如何与群体关系及制度安排有关。', '个人解释并不必然错误，但需要比较不同位置的人是否表现出稳定差异。观察座位、提问方式、教师回应和同伴反应，有助于提出更具体的问题。'], exercise: '描述一次课堂沉默，分别写出个人层面和互动层面的可能解释。', checklist: ['描述具体情境', '区分观察与猜测', '提出可进一步观察的线索'] },
    { title: '角色、规范与互动秩序', duration: 45, objective: '用角色期待解释互动中的协调与冲突。', paragraphs: ['角色是与某种社会位置相联系的行为期待。同一个人可以同时是学生、社团负责人和朋友，不同期待可能产生冲突。角色不能简单理解为个人性格。', '规范既可能写在规则里，也可能通过赞许、提醒、玩笑和排斥得到维持。分析规范时，要说明谁在什么场合对什么行为作出反应，而不是只说“大家都这样”。'], exercise: '选取一次小组合作，找出一条未写下来的规范及其维持方式。', checklist: ['角色与性格区分', '规范有具体例子', '说明互动反应'] },
    { title: '群体边界与资源差异', duration: 45, objective: '观察归属、机会与资源如何在关系中分配。', paragraphs: ['群体边界可以通过资格、语言、习惯或共同经历建立。边界既可能形成支持，也可能限制外部成员获得信息和机会。需要具体说明进入规则及其后果。', '比较两个学生获取实习信息的途径时，不能只看努力程度；可观察他们接触的组织、同伴网络和可用时间。这些差异不能只凭个别故事判断，应通过更多资料检验。'], exercise: '以校园社团为例，说明一个进入门槛及它可能带来的两种不同后果。', checklist: ['边界机制具体', '区分资源与动机', '避免以个例概括全部群体'] },
    { title: '用证据比较解释', duration: 45, objective: '为同一现象提出竞争解释和反例。', paragraphs: ['一个现象可能有多种解释。若把课堂沉默解释为对出错的担忧，可以观察匿名作答是否更积极；若解释为缺少准备，可以比较提前布置材料前后的表现。', '能说明什么证据会削弱自己的判断，才更接近可检验的解释。结论可以保持暂定，同时清晰陈述已有依据及下一步需要收集的材料。'], exercise: '选择前面一章的现象，写出两种解释及能够区分它们的观察方法。', checklist: ['解释之间有区别', '提出反证条件', '证据与结论相连'] },
  ] },
  { id: 'qualitative-reading', category: '质性研究', title: '访谈材料与质性分析', subtitle: '让每一个判断回到受访者的原话', description: '通过原创教学片段，练习访谈提问、初步编码、主题整理与证据写作。', level: '方法进阶', outcomes: ['使用开放式问题追问具体经历', '保留原文与编码的对应关系', '比较相似与相反案例形成审慎解释'], chapters: [
    { title: '提问与追问', duration: 45, objective: '围绕经历追问，避免替受访者作答。', paragraphs: ['访谈开始时可以邀请受访者讲述最近的一次经历，再追问时间、地点、人物与行动顺序。开放式提问让参与者用自己的语言组织经验。', '当受访者说“那时压力很大”，可以问“能讲讲当时具体发生了什么吗？”不要直接改写成“所以是老师要求太高，对吗？”访谈者提出的解释需要与受访者的原话区分。'], exercise: '为“我后来就不参加了”写出三条开放式追问。', checklist: ['追问具体经历', '不暗示预期答案', '允许参与者补充与纠正'] },
    { title: '从片段到初步编码', duration: 50, objective: '让编码贴近行动与含义，保留原文依据。', paragraphs: ['原创教学片段：“第一次讨论我没有说话，怕大家觉得问题太简单。后来组长说每个人都可以先写在纸上，我就写了两条。”可以先尝试“担忧同伴评价”“降低发言门槛”等编码。', '编码不是原文的唯一正确答案。写下使用该编码的理由、覆盖的片段及尚不确定的地方，便于后续与其他材料比较。一个片段可以涉及多个含义。'], exercise: '为教学片段提出两个编码，并分别引用支持该编码的原话。', checklist: ['编码与片段对应', '引用准确', '理由与原话区分'] },
    { title: '比较案例与整理主题', duration: 45, objective: '通过异同与反例检查主题，而非只统计词频。', paragraphs: ['另一个原创片段：“我不说话不是怕评价，是没看懂材料。匿名写答案也没用。”这与前一片段形成比较，提醒研究者不要把所有沉默都归入同一原因。', '主题应说明一组材料之间的关系，并交代不符合该主题的案例。主题名称越概括，越需要回到原文检查是否遮蔽了重要差异。'], exercise: '比较两个沉默案例，说明一个共同点、一个关键差异和需要补充的问题。', checklist: ['保留反例', '比较维度明确', '不以词频代替解释'] },
    { title: '写出有依据的分析段落', duration: 40, objective: '组织观点、原文、解释与边界。', paragraphs: ['分析段落可以先提出一个范围明确的判断，再展示相关原文，解释原文如何支持判断，最后讨论其他解释或适用边界。引文不能替代分析，分析也不能脱离引文。', '两个教学片段只能用于练习比较，不能据此估算整个班级的比例。正式报告需要交代材料来源、分析过程与隐私处理，避免暴露可识别的个人信息。'], exercise: '用两个教学片段写一段约二百字的比较分析，保留一条原文依据及一个结论边界。', checklist: ['观点有对应原文', '区分引用与解释', '说明适用边界'] },
  ] },
]

export type TemplateImportProgress = { courseId: string | null; uploaded: number; configured?: boolean }
// Resume within the current import so retrying a failed upload does not create another course.
export async function importCourseTemplate(template: CourseTemplate, progress: TemplateImportProgress, onProgress: (progress: TemplateImportProgress) => void) {
  let next = { ...progress }
  if (!next.courseId) {
    const course = await createCourse({ name: template.title, description: `${template.description}\n课程目标：${template.outcomes.join('；')}\n基于群学致知示范课程创建，可按教学需要修改。` })
    next = { courseId: course.id, uploaded: 0 }; onProgress(next)
  }
  if (!next.configured) {
    const { getTeachingSettings, updateTeachingSettings } = await import('../../modules/teaching-assistant')
    const settings = await getTeachingSettings(next.courseId!)
    await updateTeachingSettings(next.courseId!, { version: settings.version, objectives: template.outcomes.join('；'), rubric: settings.rubric })
    next = { ...next, configured: true }; onProgress(next)
  }
  for (let i = next.uploaded; i < template.chapters.length; i++) {
    const chapter = template.chapters[i]
    const text = `# ${chapter.title}\n\n教学目标：${chapter.objective}\n建议课时：${chapter.duration} 分钟\n\n${chapter.paragraphs.join('\n\n')}\n\n## 课堂练习\n${chapter.exercise}\n\n## 自查要点\n${chapter.checklist.map((item) => `- ${item}`).join('\n')}\n\n来源：群学致知原创示范教学材料。`
    await uploadCourseDocument(next.courseId!, new File([text], `${String(i + 1).padStart(2, '0')}-${chapter.title}.md`, { type: 'text/markdown' }))
    next = { ...next, uploaded: i + 1 }; onProgress(next)
  }
  return next.courseId!
}
