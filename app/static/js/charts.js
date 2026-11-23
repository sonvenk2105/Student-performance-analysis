document.addEventListener('DOMContentLoaded', () => {
  if (!window.Chart) return;
  const subject = window.subjectChartData;
  if (subject) {
    const canvas = document.querySelector('#subject-chart');
    const mean = subject.values.reduce((sum, value) => sum + value, 0) / Math.max(subject.values.length, 1);
    if (canvas) new Chart(canvas, {type:'bar',data:{labels:subject.labels,datasets:[{label:'Percentage',data:subject.values,backgroundColor:subject.values.map(v => v >= mean ? '#6f50b4' : '#c3b4e7'),borderRadius:6}]},options:{responsive:true,scales:{y:{beginAtZero:true,max:100,title:{display:true,text:'Percentage'}}},plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`${ctx.parsed.y.toFixed(1)}%`}}}}});
    const marks = document.querySelector('#marks-chart');
    if (marks) new Chart(marks, {type:'bar',data:{labels:subject.labels,datasets:[{label:'Obtained',data:subject.obtained,backgroundColor:'#6f50b4',borderRadius:5},{label:'Maximum',data:subject.maximum,backgroundColor:'#ded8eb',borderRadius:5}]},options:{responsive:true,scales:{y:{beginAtZero:true,title:{display:true,text:'Marks'}}}}});
  }
  const trend = window.trendChartData;
  if (trend && document.querySelector('#trend-chart')) new Chart(document.querySelector('#trend-chart'), {type:'line',data:{labels:trend.labels,datasets:[{label:'Percentage',data:trend.values,borderColor:'#6f50b4',backgroundColor:'#e9e1f8',fill:true,tension:.25}]},options:{responsive:true,scales:{y:{beginAtZero:true,max:100,title:{display:true,text:'Percentage'}}}}});
  const comparison = window.assessmentCompareData;
  if (comparison && document.querySelector('#comparison-chart')) new Chart(document.querySelector('#comparison-chart'), {type:'line',data:{labels:comparison.labels,datasets:[{label:'Assessment percentage',data:comparison.values,borderColor:'#6f50b4',backgroundColor:'#e9e1f8',fill:false,tension:.2}]},options:{responsive:true,scales:{y:{beginAtZero:true,max:100,title:{display:true,text:'Percentage'}}}}});
});
