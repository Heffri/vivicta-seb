import { expect, test } from '@playwright/test'
import { matchCitation } from '../../src/components/ask/renderAnswer'
import type { Citation, KbEntry } from '../../src/types'

const catalog: KbEntry[] = [
  {stem:'atlas_2025', report_id:'lib-atlas_2025', company:'Atlas Copco', fiscal_year:2025, pages:80, sections:['income_statement'], indexed:false, sector:'Industrials', pdf_available:false},
  {stem:'atlas_2024', report_id:'lib-atlas_2024', company:'Atlas Copco', fiscal_year:2024, pages:75, sections:[], indexed:false, sector:'Industrials', pdf_available:false},
  {stem:'4c_2025', report_id:'lib-4c_2025', company:'4C Group', fiscal_year:2025, pages:60, sections:[], indexed:false, sector:'Technology', pdf_available:true},
  {stem:'unknown_2025', report_id:'lib-unknown_2025', company:'North Example', fiscal_year:2025, pages:20, sections:[], indexed:false, sector:null, pdf_available:false},
]
const citation: Citation = {report_id:'lib-atlas_2025', stem:'atlas_2025', company:'Atlas Copco', fiscal_year:2025, page:3, quote:'Revenue 100', score:0.9}

test('citation matching never guesses a fiscal year or page', () => {
  const older = {...citation,report_id:'lib-atlas_2024',stem:'atlas_2024',fiscal_year:2024}
  expect(matchCitation('Atlas Copco',3,[citation,older])).toBeUndefined()
  expect(matchCitation('Atlas Copco FY2024',3,[citation,older])).toEqual(older)
  expect(matchCitation('Atlas Copco FY2025',4,[citation])).toBeUndefined()
  expect(matchCitation('Unknown',3,[citation])).toBeUndefined()
})

for (const tone of ['dark','light']) {
  test(`global Ask, sector map and stored sources [${tone}]`, async ({page}) => {
    const submitted: Record<string,unknown>[] = []
    const errors:string[]=[]
    let indexed = 0
    page.on('pageerror',e=>errors.push(e.message))
    await page.addInitScript(t=>localStorage.setItem('acrylic-tone',t),tone)
    await page.route('**/api/**', async route => {
      const path=new URL(route.request().url()).pathname
      if(path.endsWith('/index')) indexed++
      if(path==='/api/ask') submitted.push(route.request().postDataJSON())
      const json = path==='/api/kb' ? catalog
        : path==='/api/schemas' ? [{name:'income_statement',title:'Income statement'}]
        : path==='/api/config' ? {provider:'codex',model:'test',retrieval:'bm25'}
        : path==='/api/ask' ? {question:'Revenue?',answer:'Revenue was 100 [Atlas Copco FY2025 p.3].',citations:[citation],warnings:[],model:'test'}
        : path==='/api/kb/atlas_2025/pages/3' ? {page:3,text:'Revenue 100. Saved report page.'}
        : path==='/api/kb/atlas_2025/income_statement' ? {report_id:'lib-atlas_2025',stem:'atlas_2025',pdf_available:false,company:'Atlas Copco',fiscal_year:2025,currency:'MSEK',section:'income_statement',fields:[{key:'revenue',label:'Revenue',value:100,unit:'MSEK',period:'2025',raw_label:'Revenue',source:{page:3,quote:'Revenue 100'},confidence:0.9,evidence:[]}],checks:[],warnings:[]}
        : []
      await route.fulfill({json})
    })
    await page.goto('/')
    const nav=page.getByRole('navigation')
    await nav.getByRole('tab',{name:'Ask',exact:true}).click()
    await expect(page.getByRole('heading',{level:1})).not.toHaveText('0 reports')
    const question=page.getByRole('combobox',{name:'Question',exact:true})
    await question.fill('@NotACompany revenue?')
    await expect(page.getByRole('button',{name:'Ask',exact:true})).toBeDisabled()
    await question.fill('@Atl')
    await expect(page.getByRole('option',{name:'Atlas Copco',exact:true})).toBeVisible()
    await question.press('Enter')
    await expect(question).toHaveValue('@Atlas Copco ')
    expect(submitted).toHaveLength(0)
    await question.fill('What changed in revenue?')
    await page.getByRole('button',{name:'Ask',exact:true}).click()
    await expect.poll(()=>submitted.length).toBe(1)
    expect(submitted[0].question).toBe('What changed in revenue?')
    expect(submitted[0]).not.toHaveProperty('report_ids')
    expect(submitted[0].report_stems).toEqual(catalog.map(entry => entry.stem))
    expect(indexed).toBe(0)
    await page.getByRole('button',{name:/Atlas Copco.*2025.*p\.3/}).first().click()
    await expect(page.getByRole('region',{name:'Saved source text'})).toContainText('Revenue 100. Saved report page.')
    await nav.getByRole('tab',{name:'Company map',exact:true}).click()
    await expect(page.getByRole('heading',{name:'Knowledge map',exact:true})).toBeVisible()
    await page.getByRole('button',{name:/Industrials.*1 compan/}).click()
    await expect(page.getByRole('complementary',{name:'Company reports'})).toContainText('Atlas Copco')
    await expect(page.getByRole('complementary',{name:'Company reports'})).toContainText('2024 report')
    await page.screenshot({path:`e2e/test-results/company-map-${tone}.png`,fullPage:true})
    await page.getByRole('button',{name:'Ask about company',exact:true}).click()
    await expect(question).toHaveValue(/@Atlas Copco/)
    await question.fill('@Atlas Copco What changed in revenue?')
    await page.getByRole('button',{name:'Ask',exact:true}).click()
    await expect.poll(()=>submitted.length).toBe(2)
    expect(submitted[1].report_stems).toEqual(['atlas_2025','atlas_2024'])
    expect(submitted[1]).not.toHaveProperty('report_ids')
    await nav.getByRole('tab',{name:'Company map',exact:true}).click()
    await page.getByRole('button',{name:/Atlas Copco Industrials 2 reports/}).click()
    await page.getByRole('complementary',{name:'Company reports'}).getByRole('button',{name:'Open report',exact:true}).first().click()
    await expect(page.getByText('Saved page text. The original PDF is not available on this device.')).toBeVisible()
    await expect(page.getByText('Revenue 100. Saved report page.',{exact:true})).toBeVisible()
    await nav.getByRole('tab',{name:'Knowledge base',exact:true}).click()
    await page.getByLabel('Filter reports').fill('Atlas')
    await page.getByRole('row').filter({hasText:'atlas_2025'}).getByRole('button',{name:'Open',exact:true}).click()
    await expect(page.getByText('Revenue 100. Saved report page.',{exact:true})).toBeVisible()
    expect(errors).toEqual([])
  })
}
