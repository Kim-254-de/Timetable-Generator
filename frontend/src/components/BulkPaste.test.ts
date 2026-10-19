import { parseTable, templateCsv } from './BulkPaste'

describe('parseTable', () => {
  it('reads cells pasted from Excel (tabs) by their header names', () => {
    const rows = parseTable('Code\tBuilding\tCapacity\tRoom type\nUTC-AB3\tUTC\t120\tLecture hall\nLAB 1\tSTB\t40\tLab\n\n')
    expect(rows).toEqual([
      { code: 'UTC-AB3', building: 'UTC', capacity: '120', room_type: 'Lecture hall' },
      { code: 'LAB 1', building: 'STB', capacity: '40', room_type: 'Lab' },
    ])
  })

  it('reads a CSV file with quoted commas', () => {
    const rows = parseTable('Unit code,Unit title,Class rows\r\nCOSC 103,"Introduction, ICT","BED.ENG/LIT Y1S1 (1); BED.ECDE Y1S1"\r\n')
    expect(rows).toEqual([{ unit_code: 'COSC 103', unit_title: 'Introduction, ICT', class_rows: 'BED.ENG/LIT Y1S1 (1); BED.ECDE Y1S1' }])
  })

  it('needs a header row and at least one line', () => {
    expect(parseTable('Code\tCapacity')).toEqual([])
  })

  it('round-trips its own template', () => {
    const csv = templateCsv([{ key: 'code', label: 'Code', example: 'TC 7' }, { key: 'name', label: 'Name', example: 'A, B' }])
    expect(parseTable(csv)).toEqual([{ code: 'TC 7', name: 'A, B' }])
  })
})
