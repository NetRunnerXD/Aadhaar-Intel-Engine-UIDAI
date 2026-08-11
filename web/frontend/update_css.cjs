const fs = require('fs');
let css = fs.readFileSync('src/styles/global.css', 'utf8');

// Find start and end points for replacement
const startIdx = css.indexOf('/* App Shell */');
const endIdx = css.indexOf('.field { display: flex;');

if (startIdx !== -1 && endIdx !== -1) {
  const newCss = `/* App Shell */
.app-shell {
  display: flex;
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

/* Nav Rail */
.nav-rail {
  width: 76px;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1.5rem 0;
  z-index: 50;
  box-shadow: 1px 0 15px rgba(0, 0, 0, 0.02);
  flex-shrink: 0;
}
.nav-rail-top {
  margin-bottom: 2rem;
}
.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: linear-gradient(135deg, #3b82f6, #1d4ed8);
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 0.9rem;
  color: white;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.3);
}
.nav-rail-links {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  flex: 1;
}
.nav-item {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  background: transparent;
  border: none;
}
.nav-item:hover {
  background: rgba(255, 255, 255, 0.9);
  color: var(--accent);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}
.nav-item.active {
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: white;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.25);
}
.nav-rail-bottom {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Filter Drawer */
.filter-drawer {
  width: 320px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid var(--border);
  position: absolute;
  left: 76px;
  top: 0;
  bottom: 0;
  transform: translateX(-100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 40;
  box-shadow: 10px 0 30px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
}
.filter-drawer.open {
  transform: translateX(0);
}
.filter-drawer-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-drawer-header h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.filter-drawer-content {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.icon-btn {
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(255, 255, 255, 0.6);
  color: #475569;
  border-radius: 12px;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.icon-btn:hover { 
  background: white; 
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}

`;
  
  // Also remove .sidebar-foot
  const footStartIdx = css.indexOf('.sidebar-foot {');
  const footEndIdx = css.indexOf('/* Main */');
  
  let result = css.substring(0, startIdx) + newCss + css.substring(endIdx);
  
  if (footStartIdx !== -1 && footEndIdx !== -1) {
      result = result.replace(css.substring(footStartIdx, footEndIdx), '');
  }

  fs.writeFileSync('src/styles/global.css', result);
  console.log("CSS Updated successfully.");
} else {
  console.log("Could not find targets");
}
