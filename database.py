import sqlite3
import os
import json
from datetime import datetime
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'RITB.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        avatar_url TEXT,
        student_id TEXT,
        program TEXT,
        year TEXT,
        created_at TEXT NOT NULL
    )''')

    # News table
    c.execute('''CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        content TEXT NOT NULL,
        excerpt TEXT,
        image_url TEXT,
        author_id INTEGER,
        published_at TEXT NOT NULL,
        FOREIGN KEY(author_id) REFERENCES users(id)
    )''')

    # Events table
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        event_date TEXT NOT NULL,
        time_start TEXT,
        time_end TEXT,
        location TEXT,
        description TEXT,
        image_url TEXT,
        organizer_id INTEGER,
        registered_students TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(organizer_id) REFERENCES users(id)
    )''')

    # Faculty table
    c.execute('''CREATE TABLE IF NOT EXISTS faculty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        name TEXT NOT NULL,
        title TEXT,
        department TEXT,
        bio TEXT,
        photo_url TEXT,
        email TEXT,
        research_areas TEXT,
        publications TEXT DEFAULT '[]',
        courses TEXT DEFAULT '[]',
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        user_id  INTEGER,
        student_name TEXT NOT NULL,
        student_branch TEXT,
        status   TEXT NOT NULL DEFAULT 'absent',
        marked_at TEXT,
        UNIQUE(event_id, student_name),
        FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id)  REFERENCES users(id)  ON DELETE SET NULL
    )''')

    conn.commit()

    # -- Migrations: safely add columns that may not exist in older DBs --
    for col, defn in [
        ('registered_students', 'TEXT DEFAULT NULL'),
        ('extra_images', 'TEXT DEFAULT "[]"'),
        ('attendance_enabled', 'INTEGER DEFAULT 0'),
    ]:
        try:
            c.execute(f'ALTER TABLE events ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    for col, defn in [
        ('extra_images', 'TEXT DEFAULT "[]"'),
    ]:
        try:
            c.execute(f'ALTER TABLE news ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    for col, defn in [
        ('student_year', 'TEXT DEFAULT NULL'),
        ('rank',         'TEXT DEFAULT NULL'),
    ]:
        try:
            c.execute(f'ALTER TABLE attendance ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    # Faculty new columns migration
    for col, defn in [
        ('total_publications', 'INTEGER DEFAULT 0'),
        ('experience',         'INTEGER DEFAULT 0'),
    ]:
        try:
            c.execute(f'ALTER TABLE faculty ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    # Seed default data if empty
    try:
        _seed_data(c)
        conn.commit()
    except Exception:
        conn.rollback()
    
    conn.close()

def _seed_data(c):
    # Admin user
    c.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if c.fetchone()[0] == 0:
        now = datetime.now().isoformat()
        c.execute('''INSERT INTO users (email, password_hash, role, name, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('admin@ritb.edu', generate_password_hash('admin123'), 'admin', 'Administrator', 'active', now))
        admin_id = c.lastrowid

        # Demo teacher user
        c.execute('''INSERT INTO users (email, password_hash, role, name, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('sarah.jenkins@scholastic.edu', generate_password_hash('teacher123'), 'teacher', 'Dr. Sarah Jenkins', 'active', now))
        teacher_id = c.lastrowid

        # Demo student user
        c.execute('''INSERT INTO users (email, password_hash, role, name, status, student_id, program, year, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  ('alex.student@scholastic.edu', generate_password_hash('student123'), 'student', 'Alex Johnson', 'active', 'STU2024001', 'Computer Science', '3rd Year', now))

        # Faculty profiles
        faculty_data = [
            (teacher_id, 'Dr. Sarah Jenkins', 'Associate Professor', 'Engineering & Robotics',
             'Dr. Jenkins is a leading researcher in human-robot interaction and autonomous systems. She leads the Pulse Robotics Lab and has over 80 peer-reviewed publications.',
             'https://i.pravatar.cc/300?img=47',
             'sarah.jenkins@scholastic.edu',
             'Robotics, Human-Robot Interaction, Autonomous Systems',
             json.dumps(['Resilient Control Architectures for Decentralized Swarm Systems (2024)', 'Haptic Feedback in Minimally Invasive Surgery (2023)', 'Human-Robot Co-Navigation: Predictive Modeling (2022)']),
             json.dumps(['ENGR 401: Advanced Robotics', 'ENGR 215: Control Systems', 'ENGR 520: Graduate Seminar in HRI'])),
            (None, 'Prof. Michael Chen', 'Full Professor', 'Computer Science',
             'Professor Chen specializes in distributed computing and AI ethics. He has consulted for major tech firms and authored three textbooks on modern software architecture.',
             'https://i.pravatar.cc/300?img=12',
             'michael.chen@scholastic.edu',
             'AI Ethics, Distributed Computing, Machine Learning',
             json.dumps(['Neural Network Bias Mitigation (2024)', 'Scalable Microservice Architectures (2023)']),
             json.dumps(['CS 301: Algorithms', 'CS 480: Artificial Intelligence', 'CS 510: Ethics in Technology'])),
            (None, 'Dr. Elena Rodriguez', 'Assistant Professor', 'Life Sciences',
             'Dr. Rodriguez is pioneering research in synthetic biology and lab-grown bio-structures. Her work on cellular engineering has received international recognition.',
             'https://i.pravatar.cc/300?img=32',
             'elena.rodriguez@scholastic.edu',
             'Synthetic Biology, Cellular Engineering, Genomics',
             json.dumps(['Lab-Grown Bio-Structures: A New Frontier (2024)', 'CRISPR Applications in Tissue Engineering (2023)']),
             json.dumps(['BIO 310: Molecular Biology', 'BIO 450: Synthetic Biology', 'BIO 520: Graduate Research Methods'])),
            (None, 'Prof. James Sterling', 'Full Professor', 'Business & Economics',
             'Prof. Sterling is a renowned economist focusing on sustainable business models and climate finance. He advises government bodies on green economic policy.',
             'https://i.pravatar.cc/300?img=53',
             'james.sterling@scholastic.edu',
             'Climate Finance, Sustainable Economics, Policy Analysis',
             json.dumps(['Green Bonds and Climate Investment (2024)', 'Circular Economy Metrics for Universities (2023)']),
             json.dumps(['ECON 201: Microeconomics', 'ECON 405: Environmental Economics', 'BUS 510: Strategic Sustainability'])),
            (None, 'Dr. Maya Patel', 'Associate Professor', 'Arts & Humanities',
             'Dr. Patel merges computational methods with humanistic inquiry, exploring how data visualization can illuminate literary and historical patterns.',
             'https://i.pravatar.cc/300?img=44',
             'maya.patel@scholastic.edu',
             'Digital Humanities, Data Visualization, Literary Analysis',
             json.dumps(['Mapping the Victorian Novel (2024)', 'Algorithmic Poetics: Meaning in Generative Text (2022)']),
             json.dumps(['HUM 220: Digital Humanities', 'ENG 310: Computational Literary Studies', 'ART 400: Data as Canvas'])),
            (None, 'Prof. Robert Hynes', 'Professor Emeritus', 'Physics & Astronomy',
             'Prof. Hynes spent 35 years at the forefront of astrophysics research, contributing to our understanding of dark matter and exoplanet atmospheres.',
             'https://i.pravatar.cc/300?img=60',
             'robert.hynes@scholastic.edu',
             'Astrophysics, Dark Matter, Exoplanet Research',
             json.dumps(['Dark Matter Distribution in Spiral Galaxies (2023)', 'Atmospheric Spectroscopy of TRAPPIST-1 Planets (2021)']),
             json.dumps(['PHYS 101: Introductory Astronomy', 'PHYS 420: Astrophysics', 'PHYS 510: Special Topics in Cosmology'])),
        ]
        for f in faculty_data:
            c.execute('''INSERT INTO faculty (user_id, name, title, department, bio, photo_url, email, research_areas, publications, courses)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', f)

        # Seed news articles
        news_data = [
            ('The New Science Hub: A Vision for 2025', 'Academics',
             '''<p>After three years of planning and fundraising, the University has officially broken ground on the new <strong>Meridian Science Hub</strong>—a 120,000-square-foot interdisciplinary research complex that promises to redefine how science is studied, taught, and practiced on our campus.</p>
             <p>The $285 million facility will house state-of-the-art laboratories for biology, chemistry, physics, and engineering, as well as collaborative maker spaces and a 400-seat lecture amphitheater. The architect, renowned firm Zaha Hadid Architects, has designed a structure inspired by the double helix, with sweeping glass facades that flood the interior with natural light.</p>
             <h3>A Hub for Collaboration</h3>
             <p>"We're not just building a building," said President Marlowe at the groundbreaking ceremony. "We're building the future of academic research—a place where a biologist and an engineer can have a conversation over coffee that leads to the next great discovery."</p>
             <p>The Hub is expected to open in Fall 2026 and will accommodate over 500 researchers and 1,200 undergraduate students daily.</p>''',
             'Groundbreaking ceremony held for the new 120,000 sq-ft interdisciplinary research complex, set to open Fall 2026.',
             'https://images.unsplash.com/photo-1562774053-701939374585?w=800',
             admin_id),
            ('How AI is Reshaping the Liberal Arts Curriculum', 'Academics',
             '''<p>The Department of Humanities has launched a landmark initiative to integrate artificial intelligence tools into its core curriculum, a move that has sparked debate, excitement, and a wave of creative experimentation across campus.</p>
             <p>Beginning this spring semester, students in literature, history, and philosophy courses will use advanced language models as research assistants, analytical tools, and even as creative partners in writing workshops.</p>
             <h3>A New Kind of Literary RITB</h3>
             <p>"We are not replacing the close reading of a text," explains Dr. Maya Patel, who helped design the program. "We are giving students a lens that can read a million texts simultaneously, and then asking them: what does that tell us that we couldn't see before?"</p>''',
             'The Humanities Department integrates AI tools into core curriculum, sparking campus-wide debate and innovation.',
             'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=800',
             teacher_id),
            ('University Ranked #1 in Innovation by National Research Council', 'Research',
             '''<p>For the second consecutive year, our university has been ranked <strong>#1 in Innovation</strong> by the National Research Council's annual assessment of higher education institutions. This recognition reflects the extraordinary output of our research centers and the entrepreneurial spirit embedded in our academic culture.</p>
             <p>The ranking considers patents filed, startups founded by graduates and faculty, industry partnerships, and research funding secured. This year, the university saw a 34% increase in patent applications and established 12 new industry partnerships worth over $50 million combined.</p>''',
             'For the second year running, the university tops the National Research Council Innovation Rankings.',
             'https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=800',
             admin_id),
            ('Championship Dreams: Women\'s Basketball Enters Final Four', 'Athletics',
             '''<p>The RITB Women's Basketball team has made history, advancing to the Final Four of the national collegiate tournament for the first time in the program's 40-year history. The team, led by senior captain Jade Williams and first-year phenom Rio Tanaka, defeated the top-seeded Riverside Wolves 78-71 in a thrilling overtime showdown.</p>''',
             "The women's basketball team makes historic Final Four appearance with a dramatic overtime victory.",
             'https://images.unsplash.com/photo-1546519638-68e109498ffc?w=800',
             admin_id),
            ('The Future of Lab-Grown Bio-Structures by Dr. Elena Rodriguez', 'Research',
             '''<p>In a paper published in <em>Nature Bioengineering</em>, Dr. Elena Rodriguez of our Life Sciences department has outlined a revolutionary method for growing functional bio-structures in a laboratory setting, with implications for regenerative medicine, organ farming, and environmental remediation.</p>
             <p>The technique, dubbed "Cellular Origami Scaffolding," uses biodegradable polymer frameworks seeded with pluripotent stem cells to grow complex three-dimensional tissue structures with unprecedented fidelity.</p>''',
             'Dr. Rodriguez\'s "Cellular Origami Scaffolding" published in Nature Bioengineering has potential to transform regenerative medicine.',
             'https://images.unsplash.com/photo-1576086213369-97a306d36557?w=800',
             teacher_id),
            ('Unity Festival: Celebrating Our Global Campus', 'Social',
             '''<p>The annual <strong>Unity Festival</strong> returned this weekend with its grandest edition yet, drawing over 3,000 students, faculty, staff, and community members to the Central Quad over two days of cultural performances, culinary explorations, and artistic expression.</p>
             <p>Representing over 80 countries and more than 120 student cultural clubs, the festival featured live music stages, international food markets, fashion showcases, and interactive art installations created by students from the Fine Arts department.</p>''',
             'The annual Unity Festival celebrated over 80 countries with performances, food, and art across two vibrant days.',
             'https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=800',
             admin_id),
        ]
        for n in news_data:
            c.execute('''INSERT INTO news (title, category, content, excerpt, image_url, author_id, published_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (n[0], n[1], n[2], n[3], n[4], n[5], now))

        # Seed events
        events_data = [
            ('Annual Tech Symposium 2024', 'Academic',
             '2026-03-22', '09:00', '17:00', 'Meridian Hall, Room 101',
             'Join us for a full day of keynotes, workshops, and networking with industry leaders and innovators. This year\'s theme is "The Convergent Frontier: AI, Biology, and the Future of Work."',
             'https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800', admin_id),
            ('Homecoming Game vs. Riverside Wolves', 'Athletics',
             '2026-03-29', '15:00', '18:00', 'University Stadium, Main Field',
             'Come support our team as we take on the Riverside Wolves in this season\'s most anticipated match. Wear your colors, bring your energy, and be part of history.',
             'https://images.unsplash.com/photo-1567521464027-f127ff144326?w=800', admin_id),
            ('Fall Festival on the Quad', 'Social',
             '2026-04-05', '11:00', '20:00', 'Central Quad',
             'Three days, 50+ clubs, unlimited fun. The Annual Fall Festival transforms our Central Quad into a vibrant carnival of culture, food, and entertainment.',
             'https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=800', admin_id),
            ('Annual Dean\'s Lecture: Future of AI', 'Academic',
             '2026-03-18', '14:00', '15:30', 'Forbes Auditorium',
             'Professor Alan Turing Institute Fellow Dr. Amara Osei delivers this year\'s prestigious Dean\'s Lecture on artificial general intelligence and its societal implications.',
             'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=800', teacher_id),
            ('Resume Building & LinkedIn Mastery Workshop', 'Career',
             '2026-03-18', '16:30', '18:00', 'Career Center, Suite 200',
             'An intensive hands-on workshop with Career Services advisors and LinkedIn representatives. Transform your digital presence and walk away with a polished profile.',
             'https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=800', teacher_id),
            ('Winter Gala & Alumni Awards 2024', 'Social',
             '2026-04-12', '19:00', '23:00', 'Grand Ballroom, Campus Hotel',
             'Join us for the most prestigious evening of the academic year. Celebrate excellence, connect with history, and enjoy a night of refinement as we honor our outstanding alumni.',
             'https://images.unsplash.com/photo-1530103862676-de8c9debad1d?w=800', admin_id),
            ('Graduate Research Showcase', 'Research',
             '2026-04-20', '10:00', '16:00', 'Innovation Center, Floor 3',
             'Graduate students from all departments present their latest research findings. Open to all university members and invited industry partners.',
             'https://images.unsplash.com/photo-1576086213369-97a306d36557?w=800', teacher_id),
        ]
        for e in events_data:
            c.execute('''INSERT INTO events (title, category, event_date, time_start, time_end, location, description, image_url, organizer_id, created_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7], e[8], now))


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
