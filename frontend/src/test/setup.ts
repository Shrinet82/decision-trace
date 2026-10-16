import '@testing-library/jest-dom';

// Mock 2D canvas context for JSDOM
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = () => null;
}

window.scrollTo = () => {};
