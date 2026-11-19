import path from 'node:path';
import fs from 'node:fs';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition, openBrowser} from '@remotion/renderer';

const projectDir = path.resolve(process.argv[2] || '.');
const mainCompositionId = process.argv[3] || 'MainEssay';
const includeMid = process.argv.includes('--with-mid');
// Default to 18123 so Windows Hyper-V/WinNAT TCP port exclusions (2308-3207) never trigger 'No available ports found'
const SAFE_PORT = Number(process.env.REMOTION_PORT || 18123);

const outDir = path.join(projectDir, 'out', 'keyframes');
fs.mkdirSync(outDir, {recursive: true});

const customJsonArg = process.argv.find((a) => a.startsWith('--scenes-json='));
const scenesDataPath = customJsonArg
  ? path.resolve(projectDir, customJsonArg.slice('--scenes-json='.length))
  : path.join(projectDir, 'src', 'data', 'scenesData.json');

const sceneIds = fs.existsSync(scenesDataPath)
  ? JSON.parse(fs.readFileSync(scenesDataPath, 'utf8')).map((s) => s.id)
  : ['S01', 'S02', 'S03', 'S04', 'S05', 'S06', 'S07', 'S08', 'S09', 'S10', 'S11', 'S12'];

async function main() {
  console.log(`==> Bundling ${mainCompositionId} from ${projectDir} (port ${SAFE_PORT})...`);
  const serveUrl = await bundle({
    entryPoint: path.join(projectDir, 'src', 'index.ts'),
  });

  const browser = await openBrowser('chrome');
  const fullComp = await selectComposition({
    serveUrl,
    id: mainCompositionId,
    puppeteerInstance: browser,
    port: SAFE_PORT,
  });

  console.log(
    `==> Total: ${fullComp.durationInFrames} frames @ ${fullComp.fps}fps (${(
      fullComp.durationInFrames / fullComp.fps
    ).toFixed(2)}s)`,
  );

  for (const sid of sceneIds) {
    const comp = await selectComposition({
      serveUrl,
      id: `Scene-${sid}`,
      puppeteerInstance: browser,
      port: SAFE_PORT,
    });

    const ratios = includeMid ? [0.25, 0.48, 0.76] : [0.25, 0.76];
    const tags = includeMid ? ['A_enter', 'M_mid', 'B_climax'] : ['A_enter', 'B_climax'];

    for (let i = 0; i < ratios.length; i++) {
      const f = Math.round(comp.durationInFrames * ratios[i]);
      await renderStill({
        composition: comp,
        serveUrl,
        output: path.join(outDir, `${sid}_${tags[i]}.png`),
        frame: f,
        imageFormat: 'png',
        puppeteerInstance: browser,
        port: SAFE_PORT,
      });
    }
    console.log(`  [OK] ${sid} (${comp.durationInFrames} frames)`);
  }

  await browser.close({silent: true});
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
