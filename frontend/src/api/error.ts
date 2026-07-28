export class ApiRequestError extends Error {
  readonly status?: number

  constructor(
    message: string,
    status?: number,
  ) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}
