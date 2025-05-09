import pickle


class Index:
    def __init__(self, name):
        self.name = name
        self.msgs = []
        """
        ["1st_line", "2nd_line", "3rd_line", ...]
        Example:
        "How are you?\nI am fine.\n" will be stored as
        ["How are you?", "I am fine." ]
        """

        self.index = {}
        """
        {word1: [line_number_of_1st_occurrence,
                 line_number_of_2nd_occurrence,
                 ...]
         word2: [line_number_of_1st_occurrence,
                  line_number_of_2nd_occurrence,
                  ...]
         ...
        }
        """

        self.total_msgs = 0
        self.total_words = 0

    def get_total_words(self):
        return self.total_words

    def get_msg_size(self):
        return self.total_msgs

    def get_msg(self, n):
        return self.msgs[n]

    def add_msg(self, m: str):
        """
        m: the message to add

        updates self.msgs and self.total_msgs
        """
        # IMPLEMENTATION
        # ---- start your code ---- #
        self.msgs.extend(m.splitlines())
        self.total_msgs += len(m.splitlines())
        # ---- end of your code --- #
        return

    def add_msg_and_index(self, m):
        self.add_msg(m)
        line_at = self.total_msgs - 1
        self.indexing(m, line_at)

    def indexing(self, m, l):
        """
        updates self.total_words and self.index
        m: message, l: current line number
        """

        # IMPLEMENTATION
        # ---- start your code ---- #
        lst = m.split()
        self.total_words += len(lst)
        for word in lst:
            if not word[-1].isalpha():
                word = word[:-1]
            if word in self.index:
                if l not in self.index[word]:
                    self.index[word].append(l)
            else:
                self.index[word] = [l]

        # ---- end of your code --- #
        return

    # implement: query interface

    def search(self, term):
        """
        return a list of tupple.
        Example:
        if index the first sonnet (p1.txt),
        then search('thy') will return the following:
        [(7, " Feed'st thy light's flame with self-substantial fuel,"),
         (9, ' Thy self thy foe, to thy sweet self too cruel:'),
         (9, ' Thy self thy foe, to thy sweet self too cruel:'),
         (12, ' Within thine own bud buriest thy content,')]
        """
        msgs = []
        # IMPLEMENTATION
        # ---- start your code ---- #
        words = term.split()
        if len(words)<=1:
            for i in range(len(self.msgs)):
                for word in words:
                    if not msgs and word in self.msgs[i]:
                        msgs.append((i, self.msgs[i]))
                    elif word in self.msgs[i] and msgs[-1] != word:
                        msgs.append((i, self.msgs[i]))
        else:
            for word in words:
                if word in self.index.keys():
                    for lnum in self.index[word]:
                        msgs.append((lnum, self.msgs[lnum]))
            # ---- end of your code --- #
            temp = []
            for lum, line in msgs:
                TF = 1
                for word in words:
                    if word not in line:
                        TF = 0
                        continue
                if TF == 1 and (lum, line) not in temp:
                    temp.append((lum, line))
            msgs = temp
        result = ""
        for item in msgs:
            result += str(item[0]) + ": " + str(item[1]) + "\n" 
        return result


class PIndex(Index):
    def __init__(self, name):
        super().__init__(name)
        roman_int_f = open('roman.txt.pk', 'rb')
        self.int2roman = pickle.load(roman_int_f)
        roman_int_f.close()
        self.load_poems()

    def load_poems(self):
        """
        open the file for read, then call
        the base class's add_msg_and_index()
        """
        
        # IMPLEMENTATION
        # ---- start your code ---- #
        f = open("AllSonnets.txt", "r")
        lines = f.readlines()
        for line in lines:
            self.add_msg_and_index(line)
        f.close()
        # ---- end of your code --- #
        return

    def get_poem(self, p):
        poem = []
        # IMPLEMENTATION
        # ---- start your code ---- #
        try:
            pointer1 = f"{self.int2roman[p]}."
            pointer2 = f"{self.int2roman[p+1]}."
            left = self.msgs.index(pointer1)
            right = self.msgs.index(pointer2)
            poem.extend(self.msgs[left:right])
        except:
            pointer = f"{self.int2roman[p]}."
            left = self.msgs.index(pointer)
            poem.extend(self.msgs[left:])
        # ---- end of your code --- #
        return poem


if __name__ == "__main__":
    sonnets = PIndex("AllSonnets.txt")
    # the next two lines are just for testing
    p3 = sonnets.get_poem(3)
    for p in p3:
        print(p.lstrip())
    print()
    target = input("search for history: ")
    s_love = sonnets.search(target)
    for targets in target.split():
        s_love = str(s_love).replace(targets, f"\033[93m{targets}\033[0m")
    s_love = str(s_love).replace("), ", "),\n")
    print(s_love)
