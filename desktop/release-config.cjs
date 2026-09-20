const channel = process.env.RELEASE_CHANNEL
if (!['main', 'demo'].includes(channel)) throw new Error('RELEASE_CHANNEL must be main or demo')
const version = process.env.RELEASE_VERSION
if (!/^1\.\d+\.\d+$/.test(version || '')) throw new Error('RELEASE_VERSION must be 1.<run>.<attempt>')
module.exports = {
  extends: './electron-builder.yml',
  appId: channel === 'demo' ? 'com.vivicta.annual-report-parser' : 'com.vivicta.annual-report-parser.main',
  nsis: { artifactName: `annual-report-parser-${channel}-setup-${version}.exe` },
  productName: channel === 'demo' ? 'Annual Report Parser Demo' : 'Annual Report Parser',
  extraMetadata: {
    version,
    name: channel === 'demo' ? 'annual-report-parser-desktop' : 'annual-report-parser-desktop-main',
  },
  publish: [{
    provider: 'generic',
    url: `https://github.com/Heffri/vivicta-seb/releases/download/desktop-${channel}/`,
  }],
}
