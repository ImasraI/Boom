/** Request ownership for the inspector. Late responses never select another run. */
export class RagRequestFence {
  private active = true;
  private epoch = 0;
  private requests = new Map<string, AbortController>();

  activate() { this.active = true; }

  begin(channel: string) {
    this.invalidate(channel);
    const controller = new AbortController();
    const epoch = this.epoch;
    this.requests.set(channel, controller);
    return {
      signal: controller.signal,
      current: () => this.active && epoch === this.epoch &&
        this.requests.get(channel) === controller && !controller.signal.aborted,
    };
  }

  invalidate(channel: string) {
    this.requests.get(channel)?.abort();
    this.requests.delete(channel);
  }

  dispose() {
    this.active = false;
    this.epoch += 1;
    this.requests.forEach(controller => controller.abort());
    this.requests.clear();
  }
}
