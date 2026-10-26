"""A local interface to the real Chapter 1 morning job and planning reader."""
import argparse
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from forecast_job import HERE, run_job, read_publication, load_planning


class ServiceDemo:
    def __init__(self, root, output):
        self.root, self.output = root, output
        root.title('Chapter 1 Morning Forecast Service')
        root.geometry('1040x760+30+30')
        root.minsize(1040,760)
        root.configure(bg='white')
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TFrame', background='white')
        style.configure('TLabel', background='white', foreground='#173042', font=('Arial',16))
        style.configure('Title.TLabel', font=('Arial',25,'bold'),foreground='black')
        style.configure('Status.TLabel', font=('Arial',19,'bold'))
        style.configure('TButton',font=('Arial',15),padding=(10,6))
        style.configure('TRadiobutton',background='white',font=('Arial',16),padding=(4,3))
        style.configure('Treeview',font=('Arial',18),rowheight=35,background='white',fieldbackground='white')
        style.configure('Treeview.Heading',font=('Arial',15,'bold'),padding=5)
        frame=ttk.Frame(root,padding=16);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Morning forecast service',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Synthetic data  |  Demo clock: 5 Jan 2026, 05:00 +07:00').pack(anchor='w',pady=(3,6))
        controls=ttk.Frame(frame);controls.pack(fill='x',pady=(0,8))
        self.case=tk.StringVar(value='on-time')
        ttk.Radiobutton(controls,text='On-time feed',variable=self.case,value='on-time',command=self.select).pack(side='left')
        ttk.Radiobutton(controls,text='Late North feed',variable=self.case,value='late-feed',command=self.select).pack(side='left')
        ttk.Button(controls,text='Load planning',command=self.load).pack(side='right',padx=(6,0))
        ttk.Button(controls,text='Run morning job',command=self.run).pack(side='right')
        self.times=ttk.Label(frame,text='Cutoff 04:30  |  Publication deadline 06:00  |  Target: 6 Jan 2026')
        self.times.pack(anchor='w',pady=(0,8))
        self.status=ttk.Label(frame,text='Choose a feed and run the morning job.',style='Status.TLabel')
        self.status.pack(anchor='w',pady=(2,6))
        self.summary=ttk.Label(frame,text='No batch loaded.')
        self.summary.pack(anchor='w',pady=(0,8))
        self.detail=ttk.Label(frame,text='Primary method: mean of three sales days. Fallback: saved prior-week quantity.',wraplength=990)
        self.detail.pack(anchor='w',pady=(0,8))
        self.table=ttk.Treeview(frame,columns=('store','product','forecast','method','reason'),show='headings',height=8,selectmode='none')
        for name,title,width in zip(self.table['columns'],['Store','Product','Units','Method','Reason'],[150,150,140,180,340]):
            self.table.heading(name,text=title);self.table.column(name,width=width,anchor='center' if name=='forecast' else 'w')
        self.table.tag_configure('fallback',foreground='#A05A0B')
        self.table.tag_configure('primary',foreground='#176346')
        self.table.pack(fill='x',pady=(2,8))
        self.storage=ttk.Label(frame,text='The job publishes current.json. The planning reader follows that file.',wraplength=990)
        self.storage.pack(anchor='w',pady=(3,5))
        self.note=ttk.Label(frame,text='Forecasts support planning; this example does not calculate or send supplier orders.',wraplength=990)
        self.note.pack(anchor='w',pady=(2,0))

    def select(self):
        self.status.configure(text='Feed selected. Run the morning job.',foreground='#173042')
        self.summary.configure(text='No batch loaded for this selection.')
        for item in self.table.get_children():self.table.delete(item)

    def folder(self):
        return self.output/self.case.get()

    def show_rows(self,rows):
        for item in self.table.get_children():self.table.delete(item)
        for row in rows:
            self.table.insert('','end',values=(row['store'],row['product'],row['forecast_units'],row['method'],row['reason'] or 'on-time history'),tags=(row['method'],))

    def run(self):
        try:
            result=run_job(self.case.get(),self.folder())
            if result['status']!='published':
                self.status.configure(text='Not published: planning needs a response.',foreground='#A62E23')
                self.summary.configure(text=f"Manual items: {len(result['manual'])}")
                return
            publication,rows=read_publication(self.folder(),result['target_date'])
            self.show_rows(rows)
            self.status.configure(text='Published: 8 of 8 forecasts available',foreground='#176346')
            self.summary.configure(text=f"Primary: {result['primary']}  |  Fallback: {result['fallback']}  |  Manual: {len(result['manual'])}")
            self.detail.configure(text=('North feed available 04:31, after cutoff 04:30. North uses saved fallback; South uses primary.' if self.case.get()=='late-feed' else 'Both feeds available 04:20, before cutoff 04:30. All forecasts use the primary method.'))
            self.storage.configure(text=f"Batch: {publication['batch_id']}  |  Published at 05:00\nSaved in service_runs/{self.case.get()}/current.json")
            self.note.configure(text='Load planning to read the published batch into the planning application.')
        except (ValueError,OSError,KeyError) as error:
            self.status.configure(text=f'Job stopped: {error}',foreground='#A62E23')

    def load(self):
        try:
            result=load_planning(self.folder(),'2026-01-06')
            self.show_rows(result['tasks'])
            self.status.configure(text=f"Planning application: {result['total_for_date']} tasks for 6 Jan",foreground='#176346')
            self.summary.configure(text=f"New tasks: {result['created']}  |  Refreshed: {result['refreshed']}  |  Total for date: {result['total_for_date']}")
            self.detail.configure(text='Each task uses store + product + target date. Loading again refreshes the same task.')
            self.storage.configure(text=f"Read from service_runs/{self.case.get()}/current.json\nSaved to planning_tasks.json in the same folder")
            self.note.configure(text='Forecast quantities and fallback labels are available for planning. Planners still approve orders.')
        except (ValueError,OSError,KeyError) as error:
            self.status.configure(text=f'Planning load stopped: {error}',foreground='#A62E23')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'service_runs')
    args=parser.parse_args()
    root=tk.Tk();ServiceDemo(root,args.output);root.mainloop()


if __name__=='__main__':main()
