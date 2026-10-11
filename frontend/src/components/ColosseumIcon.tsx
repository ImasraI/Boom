/** The broken upper wall and two curved arcades keep the landmark readable at tab size. */
export default function ColosseumIcon({ size = 24, className = "" }: { size?: number; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 48 44" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className}>
    <path d="M4 15C8 8 17 4 27 3V15C34 15 40 17 44 20V35C32 40 16 40 4 35Z" fill="currentColor" fillOpacity=".08" />
    <path d="M4 15C11 11 20 10 27 10M4 21C16 16 33 16 44 21M4 28C16 23 33 23 44 28M4 35C16 30 33 30 44 35" />
    {[8, 14, 20, 26, 32, 38].map(x => {
      const curve = Math.abs(24 - x) * .12;
      return <g key={x}>
        <path d={`M${x} ${23 + curve}v-2.4a1.6 1.6 0 0 1 3.2 0v2.4`} />
        <path d={`M${x} ${31 + curve}v-3a1.6 1.6 0 0 1 3.2 0v3`} />
      </g>;
    })}
    <path d="M10 13v-1.2a1.4 1.4 0 0 1 2.8 0M17 10v-1.2a1.4 1.4 0 0 1 2.8 0M2 38c13 5 31 5 44 0" />
  </svg>;
}
