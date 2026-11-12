// Code-native decoration keeps the AI theme light and scales without a bitmap.
const star = 'M60 6 77 37 113 37 95 68 113 99 77 99 60 130 43 99 7 99 25 68 7 37 43 37Z';

export function AiBrandMark() {
 return <svg viewBox="0 0 120 136" width="31" height="35" fill="none" aria-hidden="true"><path d={star} stroke="currentColor" strokeWidth="4" strokeLinejoin="round"/></svg>;
}

export function AiGlassMaterial() {
 return <svg className="ai-material-defs" aria-hidden="true" width="0" height="0"><defs><filter id="ai-glass-refraction" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB"><feTurbulence type="fractalNoise" baseFrequency="0.018 0.025" numOctaves="1" seed="8" result="texture"/><feDisplacementMap in="SourceGraphic" in2="texture" scale="2" xChannelSelector="R" yChannelSelector="G"/></filter></defs></svg>;
}

export function AiRelief() {
 return <svg className="ai-relief" viewBox="0 0 140 156" aria-hidden="true"><defs><linearGradient id="ai-relief-fill" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#f5f5f7"/><stop offset="1" stopColor="#eeeef1"/></linearGradient><filter id="ai-relief-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="1.5" dy="2" stdDeviation="1.5" floodColor="#555564" floodOpacity=".12"/><feDropShadow dx="-.4" dy="-.6" stdDeviation=".3" floodColor="#ffffff" floodOpacity=".85"/></filter></defs><path transform="translate(10 10)" d={star} fill="url(#ai-relief-fill)" filter="url(#ai-relief-shadow)"/></svg>;
}
