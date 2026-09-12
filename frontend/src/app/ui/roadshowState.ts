import { useEffect, useState } from 'react'
import { getRoadshowSettings, saveRoadshowSettings, resetRoadshowSettings } from '../../api/roadshow'
import type { RoadshowSettings } from '../../api/roadshow'
import { useAccount } from '../../modules/account'

const cache = new Map<string, RoadshowSettings | null>()
const loading = new Map<string, Promise<RoadshowSettings | null>>()
const eventName = 'qunxue:roadshow-settings'

export function useRoadshowSettings() {
  const { sessionState } = useAccount()
  const userId = sessionState.status === 'authenticated' ? sessionState.session.user.userId : ''
  const [data, setData] = useState<RoadshowSettings | null>(null)
  useEffect(() => {
    let active = true
    setData(userId ? cache.get(userId) ?? null : null)
    const update = () => setData(userId ? cache.get(userId) ?? null : null)
    window.addEventListener(eventName, update)
    if (userId && !cache.has(userId)) {
      if (!loading.has(userId)) loading.set(userId, getRoadshowSettings().then(({ data }) => {
        const result = data ?? null
        cache.set(userId, result)
        return result
      }).catch(() => null).finally(() => loading.delete(userId)))
      void loading.get(userId)!.then(result => { if (active) setData(result) })
    }
    return () => { active = false; window.removeEventListener(eventName, update) }
  }, [userId])
  const publish = (result: RoadshowSettings) => {
    cache.set(userId, result)
    window.dispatchEvent(new Event(eventName))
    return result
  }
  return {
    data,
    async save(body: RoadshowSettings) {
      const { data } = await saveRoadshowSettings(body)
      return publish(data)
    },
    async reset() {
      const { data } = await resetRoadshowSettings()
      return publish(data)
    },
  }
}
