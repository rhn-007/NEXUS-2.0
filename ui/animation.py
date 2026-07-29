import threading
import time
import sys

from ui.status import get_status



class NexusAnimation:


    def __init__(self):

        self.running = False

        self.thread = None


        self.frames = [

            "○──○──●",

            "○──●──○",

            "●──○──○",

            "○──●──○"

        ]



    def start(self):


        if self.running:

            return


        self.running = True


        self.thread = threading.Thread(

            target=self.loop,

            daemon=True

        )


        self.thread.start()



    def loop(self):


        index = 0


        while self.running:


            status = get_status()


            if status:


                frame = self.frames[index]


                sys.stdout.write(

                    "\r"

                    f"[NEXUS] {frame} {status}..."

                )


                sys.stdout.flush()



                index = (

                    index + 1

                ) % len(self.frames)


            else:


                self.clear_line()



            time.sleep(0.25)




    def clear_line(self):


        sys.stdout.write(

            "\r" + (" " * 80) + "\r"

        )

        sys.stdout.flush()




    def stop(self):


        self.running = False



        if self.thread:


            self.thread.join(

                timeout=1

            )


            self.thread = None



        self.clear_line()





animation = NexusAnimation()
